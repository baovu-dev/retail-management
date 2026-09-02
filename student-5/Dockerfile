FROM python:3.11-slim

WORKDIR /app

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

# Default: API backend. Override CMD per service in docker-compose:
#   database: python database/app.py  (port 6005)
#   backend:  python backend/app.py   (port 5005)
#   frontend: python frontend/app.py    (port 3005)
CMD ["python", "backend/app.py"]
