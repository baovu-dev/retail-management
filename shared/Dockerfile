FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
EXPOSE 5000
CMD ["python", "-m", "flask", "--app", "backend/app.py", "run", "--host=0.0.0.0", "--port=5000"]
