FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
COPY database/requirements.txt database/requirements.txt
COPY frontend/requirements.txt frontend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir -r database/requirements.txt \
    && pip install --no-cache-dir -r frontend/requirements.txt

COPY backend backend
COPY database database
COPY frontend frontend

EXPOSE 5002 6002 3002

CMD ["python", "backend/app.py"]