"""Student 5 evidence provider: saved recommendations, browsing, and metrics."""
import os
import re

import requests

RECOMMENDATIONS_DB_API = os.getenv("RECOMMENDATIONS_DB_API", "http://localhost:6005")
TIMEOUT = 10
MAX_RECORDS = 20


def _get(path, **params):
    response = requests.get(f"{RECOMMENDATIONS_DB_API}{path}", params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def collect(user_request: str) -> dict:
    """Return recommendation records the agents can cite."""
    match = re.search(r"customer\s*(\d+)", user_request, re.IGNORECASE)
    customer_id = int(match.group(1)) if match else None
    scope = f"customer {customer_id}" if customer_id else "all customers"
    params = {"customer_id": customer_id} if customer_id else {}

    try:
        recommendations = _get("/recommendations", **params)
        history = _get("/browsing-history", **params)
        metrics = _get("/stats/metrics")
    except requests.RequestException as exc:
        return {"status": "error", "source": "recommendations-db", "error": str(exc), "records": []}

    records = []
    for item in recommendations[:MAX_RECORDS]:
        records.append({
            "id": f"recommendation {item.get('recommendation_id')}",
            "text": (
                f"customer {item.get('customer_id')}, product {item.get('recommended_product_id')}, "
                f"score {item.get('recommendation_score')}, "
                f"explanation: \"{item.get('explanation') or 'none'}\""
            ),
        })
    for item in history[:MAX_RECORDS]:
        records.append({
            "id": f"browsing {item.get('history_id')}",
            "text": (
                f"customer {item.get('customer_id')} viewed product {item.get('product_id')} "
                f"for {item.get('time_spent')} seconds at {item.get('viewed_at')}"
            ),
        })
    records.append({
        "id": "metrics",
        "text": (
            f"total recommendations {metrics.get('total_recommendations')}, "
            f"total feedback {metrics.get('total_feedback')}, "
            f"helpful rate {metrics.get('helpful_rate_percent')} percent"
        ),
    })
    return {
        "status": "success",
        "source": "recommendations-db",
        "scope": scope,
        "records": records,
    }
