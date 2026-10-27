# Stride on Render: one container runs FastAPI (127.0.0.1:8000, private) and the
# Next.js standalone server (0.0.0.0:$PORT, public, password-gated). See README
# "Deploying to Render" and render.yaml.

# ── Frontend build ──
FROM node:20-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Runtime ──
FROM python:3.13-slim
# Node 20 runtime for server.js (just the binary; the standalone build bundles its deps)
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
# tzdata: TZ=America/Los_Angeles must work (plan logic uses date.today()); trixie-slim omits it.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata libstdc++6 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
# The Node binary is copied without its source image's shared libraries. Fail at
# build time if a base-image change leaves the runtime dependencies incomplete.
RUN node --version
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Coaching code reads <repo>/docs at runtime, so keep the /app/backend + /app/docs layout.
COPY backend/app backend/app
COPY backend/alembic.ini backend/alembic.ini
COPY backend/migrations backend/migrations
COPY docs docs
COPY demo demo
COPY --from=frontend /src/frontend/.next/standalone frontend/
COPY --from=frontend /src/frontend/.next/static frontend/.next/static
COPY --from=frontend /src/frontend/public frontend/public
COPY deploy deploy

# Runs as root: Render's persistent disk at /var/data is mounted root-owned.
RUN mkdir -p /var/data

ENV PORT=10000
EXPOSE 10000
CMD ["bash", "/app/deploy/start.sh"]
