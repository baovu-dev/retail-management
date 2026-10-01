import os

import requests

RAG_URL = os.getenv("RAG_URL", "http://localhost:8200")
RAG_FEATURE = "student-5"
RAG_TIMEOUT = 120


def rag_mode_is_enabled(req) -> bool:
    enabled = os.getenv("RAG_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return False
    mode_header = req.headers.get("X-RAG-Mode", "on").strip().lower()
    return mode_header in ("1", "true", "yes", "on")


def call_rag_service(path, payload):
    response = requests.post(
        f"{RAG_URL}{path}",
        json={**payload, "feature": RAG_FEATURE},
        timeout=RAG_TIMEOUT,
    )
    return response.json()
