import os

import requests

def get_order_status(order_id: int, access_token: str) -> dict:
    if type(order_id) is not int or not 0 < order_id <= 2147483647:
        return {"error": "order_id must be a positive integer.","code": "invalid_input",}
    if (
        not isinstance(access_token, str)
        or not access_token
        or len(access_token) > 4096
    ):
        return {
            "error": "Valid shared login authentication is required.",
            "code": "unauthorized",
        }

    base = os.getenv("ORDERS_API_URL", "http://localhost:5004").rstrip("/")

    try:
        response = requests.get(
            f"{base}/api/internal/mcp/orders/{order_id}/status",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
            allow_redirects=False,
        )

        if response.status_code != 200:
            code, message = {
                400: ("invalid_input", "Invalid order ID."),
                401: (
                    "unauthorized",
                    "Authentication invalid or expired. Please try again.",
                ),
                403: ("forbidden", "Order status access denied or MCP disabled."),
                404: ("not_found", "Order not found."),
            }.get(
                response.status_code,
                ("unavailable", "Order service is unavailable."),
            )
            return {"error": message, "code": code}

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid response format")

        status = data.get("status")
        if (
            type(data.get("order_id")) is not int
            or data["order_id"] != order_id
            or not isinstance(status, str)
            or status not in {"PENDING", "CONFIRMED", "CANCELLED"}
        ):
            raise ValueError("Invalid response content")

        return {"order_id": order_id, "status": status}

    except (requests.RequestException, ValueError, AttributeError):
        return {"error": "Order service is unavailable.","code": "unavailable",}