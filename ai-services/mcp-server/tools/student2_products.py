import os
import requests

PRODUCT_DB_API = os.getenv("PRODUCT_DB_API", "http://localhost:6002")

def get_product_by_id(product_id: int) -> dict:
    if product_id <= 0:
        return {"error": "product_id must be a positive integer"}
    
    try:
        response = requests.get(
            f"{PRODUCT_DB_API}/products/{product_id}",
              timeout=5
            )
        
        if response.status_code == 404:
            return {"error": "Product not found"}

        response.raise_for_status()
        product = response.json()

    except requests.RequestException as exc:
        return {"error": f"Product database unavailable: {exc}"}

    return {
        "product_id": product.get("product_id"),
        "name": product.get("name"),
        "category": product.get("category"),
        "description": product.get("description"),
        "price": product.get("price"),
        "brand": product.get("brand"),
        "status": product.get("status"),
    }