FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY agent/ agent/
COPY app/ app/
COPY api/ api/

ENV PYTHONUNBUFFERED=1
# Streamlit adds its entry script's own directory to sys.path, not the
# project root — without this, `from src...`/`from agent...` inside
# app/ would fail to resolve.
ENV PYTHONPATH=/app

CMD ["sh", "-c", "streamlit run app/main.py --server.port=${PORT:-8080} --server.address=0.0.0.0"]
