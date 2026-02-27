FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install openai==1.30.0 httpx>=0.25.0
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
