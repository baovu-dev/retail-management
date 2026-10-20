import os
import uuid

import requests

MULTI_AGENT_SERVICE_URL = os.getenv("MULTI_AGENT_SERVICE_URL", "http://localhost:8300")
FEATURE = "student-5"

try:
    MULTI_AGENT_TIMEOUT = int(os.getenv("MULTI_AGENT_SERVICE_TIMEOUT_SECONDS", "120"))
except ValueError:
    MULTI_AGENT_TIMEOUT = 120


def multi_agent_mode_is_enabled(req) -> bool:
    enabled = os.getenv("MULTI_AGENT_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return False
    mode_header = req.headers.get("X-Multi-Agent-Mode", "on").strip().lower()
    return mode_header in ("1", "true", "yes", "on")


def is_valid_workflow_id(workflow_id: str) -> bool:
    try:
        uuid.UUID(workflow_id)
        return True
    except ValueError:
        return False


def call_multi_agent(method, path, payload=None):
    response = requests.request(
        method,
        f"{MULTI_AGENT_SERVICE_URL}{path}",
        json=payload,
        timeout=MULTI_AGENT_TIMEOUT,
    )
    return response.status_code, response.json()
