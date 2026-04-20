FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg[binary] schedule

COPY database-init/import-gtfs.py .
COPY gtfs-updater/updater.py .

CMD ["python3", "updater.py"]
