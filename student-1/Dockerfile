FROM python:3.11-slim

WORKDIR /app

# Install dependencies for both the backend and database services
COPY backend/requirements.txt ./backend-requirements.txt
COPY database/requirements.txt ./database-requirements.txt
RUN pip install --no-cache-dir -r backend-requirements.txt -r database-requirements.txt

# Copy all service code into the image
COPY backend/ ./backend/
COPY database/ ./database/
COPY frontend/ ./frontend/
COPY prompts/ ./prompts/

# Default command runs the backend (which also serves the frontend templates).
# docker-compose overrides this command for the database container to run
# database/app.py instead, using the same image for both services.
CMD ["python", "backend/app.py"]