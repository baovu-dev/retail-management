"""Student 1 evidence provider: reviews from the Reviews database API."""
import os
import re

import requests

REVIEWS_DB_API = os.getenv("REVIEWS_DB_API", "http://localhost:6001")
TIMEOUT = 10
MAX_RECORDS = 30


def collect(user_request: str) -> dict:
    """Return review records relevant to the request, each with an ID the agents can cite."""
    match = re.search(r"product\s*(\d+)", user_request, re.IGNORECASE)
    try:
        if match:
            product_id = int(match.group(1))
            scope = f"product {product_id}"
            response = requests.get(f"{REVIEWS_DB_API}/reviews/{product_id}", timeout=TIMEOUT)
        else:
            scope = "all products"
            response = requests.get(f"{REVIEWS_DB_API}/reviews", timeout=TIMEOUT)
        response.raise_for_status()
        reviews = response.json()
    except requests.RequestException as exc:
        return {"status": "error", "source": "reviews-db", "error": str(exc), "records": []}

    records = [
        {
            "id": f"review {r['review_id']}",
            "text": (
                f"product {r['product_id']}, rating {r['rating']}/5, "
                f"flagged: {'yes' if r.get('is_flagged') else 'no'}, "
                f"comment: \"{r.get('comment') or 'none'}\""
            ),
        }
        for r in reviews[:MAX_RECORDS]
    ]
    return {"status": "success", "source": "reviews-db", "scope": scope, "records": records}


if __name__ == "__main__":
    import json
    print(json.dumps(collect("Summarise customer feedback for product 103"), indent=2))