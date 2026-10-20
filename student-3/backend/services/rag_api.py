import os
import requests

RAG_URL = os.getenv(
    "RAG_URL",
    "http://localhost:8200"
)

RAG_TIMEOUT = 120

def call_rag_service(path, payload):
    response = requests.post(
        f"{RAG_URL}{path}",
        json=payload,
        timeout=RAG_TIMEOUT
    )

    response.raise_for_status()

    return response.json()