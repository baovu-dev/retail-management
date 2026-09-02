#!/usr/bin/env bash
# Student 5 — Recommendations & Chatbot
# Ports: frontend 3005 | backend API 5005 | database 6005
# Optional: Ollama at http://localhost:11434 for AI chat replies
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "Installing dependencies..."
pip3 install -q -r database/requirements.txt -r backend/requirements.txt -r frontend/requirements.txt

echo "Seeding database (if needed)..."
python3 database/init_db.py

echo "Starting database API on port 6005..."
if lsof -i :6005 >/dev/null 2>&1; then
  echo "  Port 6005 already in use — assuming database is already running."
else
  python3 database/app.py &
  DB_PID=$!
fi

sleep 2

echo "Starting API backend on port 5005..."
if lsof -i :5005 >/dev/null 2>&1; then
  echo "  Port 5005 already in use — assuming backend is already running."
else
  python3 backend/app.py &
  BACKEND_PID=$!
fi

sleep 1

echo "Starting frontend on port 3005..."
if lsof -i :3005 >/dev/null 2>&1; then
  echo "  Port 3005 already in use — assuming frontend is already running."
else
  python3 frontend/app.py &
  FRONTEND_PID=$!
fi

echo ""
echo "✓ Student 5 is running"
echo "  Frontend:  http://localhost:3005"
echo "  Backend:   http://localhost:5005"
echo "  Database:  http://localhost:6005"
echo ""
echo "Press Ctrl+C to stop all services."

cleanup() {
  [ -n "${DB_PID:-}" ] && kill "$DB_PID" 2>/dev/null || true
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
