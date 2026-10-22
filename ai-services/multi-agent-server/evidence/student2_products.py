"""Student 2 evidence provider: Product Management records."""

import os
import re

import requests

PRODUCTS_DB_API = os.getenv("PRODUCTS_DB_API", "http://localhost:6002")
TIMEOUT = 10
MAX_RECORDS = 30

def collect(user_request: str) -> dict:
    """Collect product records for the shared multi-agent workflow."""
    match = re.search(r"product\s*(?:id\s*)?#?(\d+)", user_request, re.IGNORECASE)

    try: 
        if match:
            product_id = int(match.group(1))
            scope = f"product {product_id}"
            response = requests.get(
                f"{PRODUCTS_DB_API}/products/{product_id}", 
                timeout=TIMEOUT,
            )
            
        else:
           scope = "all products"
           response = requests.get(
               f"{PRODUCTS_DB_API}/products", 
               timeout=TIMEOUT,
        )

        response.raise_for_status()
        products = response.json()

    except requests.RequestException as exc:
        return {
            "status": "error", 
            "source": "products-db", 
            "error": str(exc), 
            "records": []
        }

    if isinstance(products, dict):
        products = [products]

    records = [
        {
            "id": f"product {p['product_id']}",
            "text": (
                f"name: {p.get('name', '')}, "
                f"category: {p.get('category', '')}, "
                f"brand: {p.get('brand', '')}, "
                f"price: {p.get('price', '')}, "
                f"status: {p.get('status', '')}, "
                f"description: {p.get('description', '')}"
            ),
        }
        for p in products[:MAX_RECORDS]
    ]

    return {
        "status": "success",
        "source": "products-db",
        "scope": scope,
        "records": records
    }
