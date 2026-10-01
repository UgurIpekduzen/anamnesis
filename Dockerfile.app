# Production image for the combined FastAPI + React service.
# Not used by local dev — docker-compose.yml runs the frontend's own Vite
# dev server and the api service separately, via the plain Dockerfile.

FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

# uv (pinned) installs exactly what uv.lock says — --frozen fails the build
# instead of silently re-resolving to whatever is newest today.
COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /bin/uv
ENV UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

COPY src/ src/
COPY agent/ agent/
COPY api/ api/
# Served by api/main.py's StaticFiles mount — see the check there for
# _FRONTEND_DIST, which is exactly this path.
COPY --from=frontend-build /frontend/dist/ frontend_dist/

ENV PYTHONUNBUFFERED=1

# Not root: the app only reads its own files and talks to Google APIs with
# the service account Cloud Run gives it, so a flaw in it should not start
# with root in the container. /app stays root-owned and read-only for this
# user.
RUN useradd --system --no-create-home --uid 10001 app
# The numeric id, not the name: some container runtimes (Cloud Run
# included) check USER against a numeric uid, not /etc/passwd.
USER 10001

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
