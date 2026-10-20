import os
import requests

CUSTOMERS_DB_API = os.getenv(
    "CUSTOMERS_DB_API",
    "http://localhost:6003"
)

def get_customer_summary(customer_id: int) -> dict:
    if customer_id <= 0:
        return {
            "error": "customer_id must be a positive integer"
        }

    try:
        response = requests.get(
            f"{CUSTOMERS_DB_API}/customers/{customer_id}",
            timeout=5
        )

        if response.status_code == 404:
            return {
                "error": "Customer not found",
                "customer_id": customer_id
            }

        response.raise_for_status()
        customer = response.json()

    except requests.RequestException as exc:
        return {
            "error": f"Customer database unavailable: {exc}"
        }

    return {
        "customer_id": customer.get("customer_id"),
        "first_name": customer.get("first_name"),
        "last_name": customer.get("last_name"),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "status": customer.get("status"),
        "created_at": customer.get("created_at")
    }