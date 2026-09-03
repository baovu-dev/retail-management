FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt ./backend-requirements.txt
COPY database/requirements.txt ./database-requirements.txt
COPY frontend/requirements.txt ./frontend-requirements.txt

RUN pip install --no-cache-dir \
    -r backend-requirements.txt \
    -r database-requirements.txt \
    -r frontend-requirements.txt

COPY backend/ ./backend/
COPY database/ ./database/
COPY frontend/ ./frontend/
COPY prompts/ ./prompts/

EXPOSE 3004 5004 6004

CMD ["python", "backend/app.py"]