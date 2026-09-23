# Production image for the combined FastAPI + React service (APPCE-56).
# Not used by local dev — docker-compose.yml runs the frontend's own Vite
# dev server and the api service separately, via the plain Dockerfile.

FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY agent/ agent/
COPY api/ api/
# Served by api/main.py's StaticFiles mount — see the check there for
# _FRONTEND_DIST, which is exactly this path.
COPY --from=frontend-build /frontend/dist/ frontend_dist/

ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
