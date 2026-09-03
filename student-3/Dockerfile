FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
COPY database/requirements.txt database/requirements.txt

RUN pip install --no-cache-dir \
-r backend/requirements.txt \
-r database/requirements.txt

COPY backend/ backend/
COPY database/ database/
COPY frontend/ frontend/

EXPOSE 5003
EXPOSE 6003

CMD ["python", "backend/app.py"]