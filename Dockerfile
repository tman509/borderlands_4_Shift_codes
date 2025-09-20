FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Expect a mounted .env or environment variables set at runtime
CMD ["python", "main.py"]
