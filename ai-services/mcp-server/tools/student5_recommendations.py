"""Read-only recommendation tools. No create, update, or delete operations."""

import os

import requests

RECOMMENDATIONS_DB_API = os.getenv("RECOMMENDATIONS_DB_API", "http://localhost:6005")


def _get(path, **params):
    try:
        response = requests.get(f"{RECOMMENDATIONS_DB_API}{path}", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"error": f"Recommendations database unavailable: {exc}"}


def get_customer_recommendations(customer_id: int) -> dict:
    if customer_id <= 0:
        return {"error": "customer_id must be a positive integer"}
    payload = _get("/recommendations", customer_id=customer_id)
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    return {
        "customer_id": customer_id,
        "count": len(payload),
        "recommendations": payload,
    }


def get_recommendation_metrics() -> dict:
    payload = _get("/stats/metrics")
    if isinstance(payload, dict) and "error" in payload and "total_recommendations" not in payload:
        return payload
    return payload


def get_customer_browsing_history(customer_id: int) -> dict:
    if customer_id <= 0:
        return {"error": "customer_id must be a positive integer"}
    payload = _get("/browsing-history", customer_id=customer_id)
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    return {
        "customer_id": customer_id,
        "count": len(payload),
        "browsing_history": payload,
    }
