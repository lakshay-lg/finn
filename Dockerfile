FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "httpx>=0.27"
COPY backend ./backend
COPY web ./web
# data snapshot: free hosts wipe their disk on restart, so the app starts from this
COPY seed ./data
ENV PYTHONPATH=/app/backend PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn finn.main:app --host 0.0.0.0 --port ${PORT}"]
