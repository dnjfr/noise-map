FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fix-shape-rfn.py .

CMD ["python3", "fix-shape-rfn.py"]

