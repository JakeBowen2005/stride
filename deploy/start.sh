#!/usr/bin/env bash
# Container entrypoint: FastAPI on 127.0.0.1:8000 (private), then Next.js on
# 0.0.0.0:$PORT. If either process dies the container exits non-zero, so Render restarts it.
set -euo pipefail
PORT="${PORT:-10000}"

# One-time Garmin token bootstrap from a secret env var. The disk copy wins afterwards,
# because garminconnect refreshes the tokens there.
if [ -n "${GARMIN_TOKENS_JSON:-}" ] && [ -n "${GARMIN_TOKENSTORE:-}" ] \
   && [ ! -f "$GARMIN_TOKENSTORE/garmin_tokens.json" ]; then
  mkdir -p "$GARMIN_TOKENSTORE"
  chmod 700 "$GARMIN_TOKENSTORE"
  (umask 077 && printf '%s' "$GARMIN_TOKENS_JSON" > "$GARMIN_TOKENSTORE/garmin_tokens.json")
  chmod 600 "$GARMIN_TOKENSTORE/garmin_tokens.json"
  echo "start.sh: wrote Garmin tokens to $GARMIN_TOKENSTORE"
fi

# One-time data import: an uploaded snapshot at /var/data/stride-upload.db replaces the DB
# before the backend opens it. The previous DB (and its -wal/-shm) is kept as a timestamped backup.
DB_PATH="${DATABASE_URL:-}"
DB_PATH="${DB_PATH#sqlite:///}"
UPLOAD="$(dirname "$DB_PATH")/stride-upload.db"
if [[ "${DATABASE_URL:-}" == sqlite:////* ]] && [ -f "$UPLOAD" ]; then
  STAMP="$(date +%Y%m%d-%H%M%S)"
  for suffix in "" -wal -shm; do
    if [ -f "$DB_PATH$suffix" ]; then mv "$DB_PATH$suffix" "$DB_PATH.before-import-$STAMP$suffix"; fi
  done
  mv "$UPLOAD" "$DB_PATH"
  echo "start.sh: imported $UPLOAD as $DB_PATH (old DB kept as *.before-import-$STAMP)"
fi

cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log &
BACKEND_PID=$!
FRONTEND_PID=""
trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true' EXIT
trap 'exit 143' TERM INT  # Render stops the container with SIGTERM

for _ in $(seq 1 60); do
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" 2>/dev/null; then
    break
  fi
  kill -0 "$BACKEND_PID" 2>/dev/null || { echo "start.sh: backend exited during startup" >&2; exit 1; }
  sleep 1
done
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" \
  || { echo "start.sh: backend never became healthy" >&2; exit 1; }

cd /app/frontend
HOSTNAME=0.0.0.0 PORT="$PORT" node server.js &
FRONTEND_PID=$!

# Exit non-zero as soon as either process dies (the EXIT trap stops the other one).
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 2
done
echo "start.sh: backend or frontend exited; stopping" >&2
exit 1
