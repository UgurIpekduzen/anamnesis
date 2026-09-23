FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
