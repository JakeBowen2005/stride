#!/usr/bin/env bash
# Start Stride (backend + frontend) and print the URL for your phone.
#   ./start.sh        production build — fast, best for using on your phone
#   ./start.sh dev    hot-reload dev mode — for working on the code
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-prod}"

# Already running (e.g. in another terminal tab)? Don't start a second copy.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 || lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<your-mac-ip>")"
  echo "Stride is already running (port 8000 or 3000 is in use)."
  echo "  On this computer:  http://localhost:3000"
  echo "  On your phone:     http://$LAN_IP:3000"
  echo "To restart it, press Ctrl+C in the terminal where it's running, then run ./start.sh again."
  exit 0
fi

# ── Backend ──
cd "$ROOT/backend"
if [ ! -d venv ]; then
  echo "Creating Python venv..."
  python3 -m venv venv
fi
venv/bin/pip install -q -r requirements.txt
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null' EXIT

# ── Frontend ──
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
if [ "$MODE" = "dev" ]; then
  npx next dev -H 0.0.0.0 -p 3000 &
else
  npm run build
  npx next start -H 0.0.0.0 -p 3000 &
fi
FRONTEND_PID=$!
trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<your-mac-ip>")"
TS_IP="$(command -v tailscale >/dev/null && tailscale ip -4 2>/dev/null | head -1 || true)"
sleep 3
if ! kill -0 "$BACKEND_PID" 2>/dev/null || ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
  echo "Stride failed to start — see the errors above."
  exit 1
fi
echo
echo "  Stride is running"
echo "  On this computer:  http://localhost:3000"
echo "  On your phone:     http://$LAN_IP:3000   (same Wi-Fi)"
[ -n "$TS_IP" ] && echo "  Anywhere (Tailscale): http://$TS_IP:3000"
echo "  Garmin auto-sync runs every 10 min while this window is open. Ctrl+C to stop."
echo
wait
