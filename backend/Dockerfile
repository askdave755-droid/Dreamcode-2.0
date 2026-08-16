FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Shell form so $PORT is expanded at container start (Railway injects PORT).
# Falls back to 8000 for local runs.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
