FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY railway-producer.py .

CMD ["python", "-u", "railway-producer.py"]
