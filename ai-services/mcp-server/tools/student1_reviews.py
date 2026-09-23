import os
import requests

REVIEWS_DB_API = os.getenv("REVIEWS_DB_API", "http://localhost:6001")

def get_rating_summary(product_id: int) -> dict:
    if product_id <= 0:
        return {"error": "product_id must be a positive integer"}
    try:
        response = requests.get(f"{REVIEWS_DB_API}/reviews/{product_id}", timeout=5)
        response.raise_for_status()
        reviews = response.json()
    except requests.RequestException as exc:
        return {"error": f"Reviews database unavailable: {exc}"}

    ratings = [r["rating"] for r in reviews]
    if not ratings:
        return {"product_id": product_id, "review_count": 0, "average_rating": None}
    return {
        "product_id": product_id,
        "review_count": len(ratings),
        "average_rating": round(sum(ratings) / len(ratings), 2),
    }
