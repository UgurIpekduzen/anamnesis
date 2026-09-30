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

ENV PYTHONUNBUFFERED=1
# uvicorn (and the other entry points local dev overrides this CMD with —
# see docker-compose.yml) is invoked directly, not via `python -m`, so the
# working directory isn't added to sys.path on its own — without this,
# `from src...`/`from agent...` would fail to resolve.
ENV PYTHONPATH=/app

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
