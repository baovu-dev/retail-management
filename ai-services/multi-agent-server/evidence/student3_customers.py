"""Aggregate customer evidence without names, contact details or account IDs."""

import os
from collections import Counter

import requests


CUSTOMERS_DB_API = os.getenv("CUSTOMERS_DB_API", "http://localhost:6003").rstrip("/")


def collect(_user_request: str) -> dict:
    """Read customer accounts but disclose only counts to the agent and history."""
    try:
        response = requests.get(f"{CUSTOMERS_DB_API}/customers", timeout=10)
        response.raise_for_status()
        customers = response.json()
        if not isinstance(customers, list) or any(not isinstance(item, dict) for item in customers):
            raise ValueError("Invalid customer evidence")
        statuses = [item.get("status") for item in customers]
        if any(not isinstance(status, str) or status.strip().lower() not in {"active", "inactive"}
               for status in statuses):
            raise ValueError("Unknown customer status")
        counts = Counter(status.strip().lower() for status in statuses)
        records = [{"id": "customer total", "text": f"Total customer accounts: {len(customers)}."}]
        records += [{"id": f"status {status}", "text": f"{status.title()} customer accounts: {counts[status]}."}
                    for status in ("active", "inactive")]
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return {"status": "error", "source": "customers-db", "error": "Customer aggregate unavailable", "records": []}
    return {"status": "success", "source": "customers-db", "scope": "aggregate account status", "records": records}
