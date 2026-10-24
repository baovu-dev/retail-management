"""Public Orders evidence for a staff review; never retrieve customer records."""
import os
from pathlib import Path

import requests


ORDERS_API = os.getenv("ORDERS_API", "http://localhost:5004").rstrip("/")
KNOWLEDGE = Path(__file__).resolve().parents[2] / "rag-server" / "knowledge" / "student-4"
DOCUMENTS = ("order-statuses.md", "order-cancellation.md")


def collect(user_request: str) -> dict:
    """Return a live aggregate and current Orders rules without personal data."""
    try:
        response = requests.get(f"{ORDERS_API}/api/orders/count", timeout=5)
        response.raise_for_status()
        count = response.json().get("count")
        if type(count) is not int or count < 0:
            raise ValueError("Invalid Orders count")
        records = [{"id": "orders count", "text": f"Total orders currently recorded: {count}."}]
        for filename in DOCUMENTS:
            content = (KNOWLEDGE / filename).read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError("Empty Orders guidance")
            records.append({"id": f"knowledge/student-4/{filename}", "text": content.strip()})
    except (requests.RequestException, ValueError, OSError, AttributeError):
        return {"status": "error", "source": "orders-public-evidence", "error": "Orders evidence unavailable", "records": []}
    return {"status": "success", "source": "orders-public-evidence", "scope": "aggregate and guidance", "records": records}
