FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY import-gtfs.py .
COPY assign-shapes.py .
COPY updater.py .

CMD ["python3", "updater.py"]

