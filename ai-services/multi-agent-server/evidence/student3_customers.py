"""Student 3 evidence provider: safe customer account records from the Customer database API."""

import os
import re

import requests


CUSTOMERS_DB_API = os.getenv(
    "CUSTOMERS_DB_API",
    "http://localhost:6003"
)

TIMEOUT = 10
MAX_RECORDS = 20


def collect(user_request: str) -> dict:
    """Return safe customer records relevant to the request."""

    match = re.search(
        r"customer\s*(\d+)",
        user_request,
        re.IGNORECASE
    )

    try:
        if match:
            customer_id = int(match.group(1))
            scope = f"customer {customer_id}"

            response = requests.get(
                f"{CUSTOMERS_DB_API}/customers/{customer_id}",
                timeout=TIMEOUT,
            )

            if response.status_code == 404:
                return {
                    "status": "success",
                    "source": "customers-db",
                    "scope": scope,
                    "records": [],
                }

            response.raise_for_status()

            customers = [response.json()]

        else:
            scope = "all customers"

            response = requests.get(
                f"{CUSTOMERS_DB_API}/customers",
                timeout=TIMEOUT,
            )

            response.raise_for_status()

            customers = response.json()

    except requests.RequestException as exc:
        return {
            "status": "error",
            "source": "customers-db",
            "error": str(exc),
            "records": [],
        }

    records = [
        {
            "id": f"customer {customer.get('customer_id')}",
            "text": (
                f"name {customer.get('first_name', '')} "
                f"{customer.get('last_name', '')}, "
                f"email {customer.get('email', '')}, "
                f"phone {customer.get('phone') or 'not provided'}, "
                f"status {customer.get('status', '')}, "
                f"created {customer.get('created_at', '')}"
            ),
        }
        for customer in customers[:MAX_RECORDS]
    ]

    return {
        "status": "success",
        "source": "customers-db",
        "scope": scope,
        "records": records,
    }