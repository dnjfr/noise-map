FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aircraft-producer.py .

CMD ["python", "-u", "aircraft-producer.py"]