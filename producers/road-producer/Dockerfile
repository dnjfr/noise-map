FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libspatialindex-dev libgeos-dev libproj-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY road-producer.py .

CMD ["python", "-u", "road-producer.py"]
