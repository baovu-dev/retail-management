import os
import math

import requests
from flask import Flask, g, jsonify, request
from flask_cors import CORS

from prompt_loader import load_prompt
from orders_auth import bearer_token, mcp_enabled, valid_order_id, verify_access_token, verify_crud_token
from purchase_auth import verify_purchase_proof
from orders_rag import rag_bp
from orders_multi_agent import multi_agent_bp


app = Flask(__name__)
CORS(app, origins=[os.getenv("ORDERS_FRONTEND_ORIGIN", "http://localhost:3004")],
     supports_credentials=False, allow_headers=["Authorization", "Content-Type"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
app.register_blueprint(rag_bp)
app.register_blueprint(multi_agent_bp)


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "http://localhost:6004"
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:0.5b"
)


class DbResponse:
    def __init__(
        self,
        status_code=503,
        data=None
    ):
        self.status_code = status_code

        self._data = data or {
            "error":
                "Order database service is unavailable."
        }

    def json(self):
        return self._data


def db_get(path):
    try:
        return requests.get(
            f"{DATABASE_URL}{path}",
            timeout=5
        )

    except requests.RequestException as error:
        print(
            f"Database GET error: {error}"
        )

        return DbResponse()


def db_post(path, payload):
    try:
        return requests.post(
            f"{DATABASE_URL}{path}",
            json=payload,
            timeout=5
        )

    except requests.RequestException as error:
        print(
            f"Database POST error: {error}"
        )

        return DbResponse()


def db_put(path, payload):
    try:
        return requests.put(
            f"{DATABASE_URL}{path}",
            json=payload,
            timeout=5
        )

    except requests.RequestException as error:
        print(
            f"Database PUT error: {error}"
        )

        return DbResponse()


def db_delete(path):
    try:
        return requests.delete(
            f"{DATABASE_URL}{path}",
            timeout=5
        )

    except requests.RequestException as error:
        print(
            f"Database DELETE error: {error}"
        )

        return DbResponse()


def call_order_status(order_id, access_token):
    # Keep existing CRUD / AI available even when MCP is disabled or not installed.
    from orders_mcp_client import call_order_status as call
    return call(order_id, access_token)


@app.post("/api/mcp/order-status")
def mcp_order_status():
    if not mcp_enabled():
        return jsonify(error="MCP Mode is disabled.", code="disabled"), 403
    data = request.get_json(silent=True)
    order_id = data.get("order_id") if isinstance(data, dict) else None
    if not valid_order_id(order_id):
        return jsonify(error="order_id must be a positive integer.", code="invalid_input"), 400
    token = bearer_token(request)
    _, error = verify_access_token(token, order_id)
    if error:
        return jsonify(error[0]), error[1]
    try:
        result = call_order_status(order_id, token)
        if "error" in result:
            status = {"invalid_input": 400, "unauthorized": 401, "forbidden": 403,
                      "not_found": 404, "unavailable": 503}.get(result.get("code"), 502)
            return jsonify(result), status
        if result.get("order_id") != order_id or result.get("status") not in {"PENDING", "CONFIRMED", "CANCELLED"}:
            raise ValueError("Invalid MCP result")
        return jsonify(order_id=order_id, status=result["status"], source="mcp", tool="get_order_status")
    except Exception:
        # Do not expose exception details that may contain bearer credentials.
        return jsonify(error="Shared MCP server is unavailable.", code="unavailable"), 503


@app.get("/api/internal/mcp/orders/<int:order_id>/status")
def internal_order_status(order_id):
    if not mcp_enabled():
        return jsonify(error="MCP Mode is disabled.", code="disabled"), 403
    if not valid_order_id(order_id):
        return jsonify(error="Invalid order ID.", code="invalid_input"), 400
    claims, error = verify_access_token(bearer_token(request), order_id)
    if error:
        return jsonify(error[0]), error[1]
    response = db_get(f"/orders/{order_id}")
    if response.status_code == 404:
        return jsonify(error="Order not found.", code="not_found"), 404
    if response.status_code != 200:
        return jsonify(error="Order database service is unavailable.", code="unavailable"), 503
    try:
        order = response.json()
        if claims["role"] != "staff" and order["customer_id"] != claims["customer_id"]:
            return jsonify(error="Order status access denied.", code="forbidden"), 403
        return jsonify(order_id=order["order_id"], status=order["status"])
    except (ValueError, KeyError, TypeError):
        return jsonify(error="Invalid order database response.", code="unavailable"), 503


def ask_ollama(prompt):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        return (
            data
            .get("response", "")
            .strip()
        )

    except requests.RequestException as error:
        print(
            f"Ollama error: {error}"
        )

        return None


@app.route(
    "/api/health",
    methods=["GET"]
)
def health():
    db_response = db_get(
        "/health"
    )

    database_connected = (
        db_response.status_code
        == 200
    )

    return jsonify({
        "status":
            "ok"
            if database_connected
            else "degraded",

        "backend_port":
            5004,

        "database_port":
            6004,

        "database_connected":
            database_connected
    }), (
        200
        if database_connected
        else 503
    )


@app.post("/api/orders/verified-purchase")
def verified_purchase():
    data = request.get_json(silent=True)
    product_id = data.get("product_id") if isinstance(data, dict) else None
    claims, error = verify_purchase_proof(bearer_token(request), product_id)
    if error:
        return jsonify(error[0]), error[1]
    try:
        response = db_post("/orders/verified-purchase", {"customer_id": claims["customer_id"], "product_id": product_id})
        result = response.json()
        if response.status_code != 200 or not isinstance(result, dict) or type(result.get("verified_purchase")) is not bool:
            raise ValueError("Invalid purchase result")
        answer = jsonify(verified_purchase=result["verified_purchase"])
        answer.headers["Cache-Control"] = "no-store"
        return answer
    except (requests.RequestException, ValueError, TypeError):
        return jsonify(error="Purchase verification unavailable.", code="unavailable"), 503


def access_error(code="forbidden", status=403):
    return jsonify(error="Orders access denied.", code=code), status


def authenticated_order(order_id, claims):
    if not valid_order_id(order_id):
        return None, (jsonify(error="Invalid order ID.", code="invalid_input"), 400)
    response = db_get(f"/orders/{order_id}")
    if response.status_code == 404:
        return None, (jsonify(error="Order not found.", code="not_found"), 404)
    if response.status_code != 200:
        return None, (jsonify(error="Orders database unavailable.", code="unavailable"), 503)
    try:
        order = response.json()
        if (not isinstance(order, dict) or order.get("order_id") != order_id
                or not valid_order_id(order.get("customer_id"))):
            raise ValueError("Invalid database order")
        if claims["role"] == "customer" and order["customer_id"] != claims["customer_id"]:
            return None, access_error()
        return order, None
    except (ValueError, TypeError, KeyError):
        return None, (jsonify(error="Invalid Orders database response.", code="unavailable"), 503)


@app.before_request
def protect_orders_crud():
    if request.method == "OPTIONS":
        return None
    protected = {"get_orders", "get_order", "create_order", "update_order", "cancel_order"}
    enabled_ai = (request.endpoint == "order_assistant"
                  and os.getenv("AI_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
    if request.endpoint in protected or enabled_ai:
        claims, error = verify_crud_token(bearer_token(request))
        if error:
            return jsonify(error[0]), error[1]
        g.orders_identity = claims
    return None


@app.get("/api/orders")
def get_orders():
    claims = g.orders_identity
    supplied = request.args.get("customer_id")
    customer_id = claims.get("customer_id") if claims["role"] == "customer" else None
    if supplied is not None:
        if not supplied.isdecimal() or not valid_order_id(int(supplied)):
            return access_error("invalid_input", 400)
        if claims["role"] == "customer" and int(supplied) != customer_id:
            return access_error()
        customer_id = int(supplied)
    path = "/orders" + (f"?customer_id={customer_id}" if customer_id else "")
    response = db_get(path)
    if response.status_code != 200:
        return access_error("unavailable", 503)
    rows = response.json()
    if not isinstance(rows, list) or any(not isinstance(row, dict) or
            claims["role"] == "customer" and row.get("customer_id") != customer_id for row in rows):
        return access_error("unavailable", 503)
    return jsonify(rows)


@app.get("/api/orders/<int:order_id>")
def get_order(order_id):
    order, error = authenticated_order(order_id, g.orders_identity)
    return error if error else jsonify(order)


@app.post("/api/orders")
def create_order():
    claims = g.orders_identity
    if claims["role"] != "customer":
        return access_error()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
        return jsonify(error="Order items are required.", code="invalid_input"), 400
    if "customer_id" in data and (type(data["customer_id"]) is not int or data["customer_id"] != claims["customer_id"]):
        return access_error()
    if any(not isinstance(item, dict) for item in data["items"]):
        return jsonify(error="Invalid order items.", code="invalid_input"), 400
    if any(not valid_order_id(item.get("product_id")) or type(item.get("quantity")) is not int
           or item["quantity"] <= 0 or type(item.get("unit_price")) not in (int, float)
           or not math.isfinite(item["unit_price"]) or item["unit_price"] < 0 for item in data["items"]):
        return jsonify(error="Invalid product, quantity or price.", code="invalid_input"), 400
    if any(item.get("product_name") is not None and
           (not isinstance(item["product_name"], str) or not 0 < len(item["product_name"].strip()) <= 120) for item in data["items"]):
        return jsonify(error="Invalid product display name.", code="invalid_input"), 400
    items = [{key: item[key] for key in ("product_id", "quantity", "unit_price")} for item in data["items"]]
    for original, item in zip(data["items"], items):
        if isinstance(original.get("product_name"), str):
            item["product_name"] = original["product_name"].strip()
    response = db_post("/orders", {"customer_id": claims["customer_id"], "items": items})
    return jsonify(response.json()), response.status_code


@app.put("/api/orders/<int:order_id>")
def update_order(order_id):
    if g.orders_identity["role"] != "staff":
        return access_error()
    order, error = authenticated_order(order_id, g.orders_identity)
    if error:
        return error
    data = request.get_json(silent=True)
    status = data.get("status") if isinstance(data, dict) else None
    if not isinstance(status, str) or status not in {"CONFIRMED", "CANCELLED"}:
        return jsonify(error="Staff may confirm or cancel an order.", code="invalid_input"), 400
    if order.get("status") == "CANCELLED" and status != "CANCELLED":
        return jsonify(error="Cancelled orders cannot be reopened.", code="invalid_transition"), 409
    response = db_put(f"/orders/{order_id}", {"status": status})
    return jsonify(response.json()), response.status_code


@app.delete("/api/orders/<int:order_id>")
def cancel_order(order_id):
    _, error = authenticated_order(order_id, g.orders_identity)
    if error:
        return error
    response = db_delete(f"/orders/{order_id}")
    return jsonify(response.json()), response.status_code


@app.route(
    "/api/orders/count",
    methods=["GET"]
)
def order_count():
    response = db_get(
        "/orders/count"
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/api/order-assistant",
    methods=["POST"]
)
def order_assistant():
    if os.getenv("AI_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return jsonify(error="AI Mode is disabled.", code="disabled"), 403
    data = request.json or {}

    question = str(
        data.get(
            "question",
            ""
        )
    ).strip()

    order_id = data.get(
        "order_id"
    )


    if not question:
        return jsonify({
            "error":
                "question is required"
        }), 400


    if order_id is None:
        return jsonify({
            "error":
                "order_id is required"
        }), 400


    try:
        order_id = int(
            order_id
        )

    except (
        TypeError,
        ValueError
    ):
        return jsonify({
            "error":
                "order_id must be an integer"
        }), 400


    order, error = authenticated_order(order_id, g.orders_identity)
    if error:
        return error

    order_context = (
        f"Order ID: "
        f"{order['order_id']}\n"

        f"Customer ID: "
        f"{order['customer_id']}\n"

        f"Status: "
        f"{order['status']}\n"

        f"Total amount: "
        f"${order['total_amount']}\n"

        f"Order date: "
        f"{order['order_date']}\n"

        f"Items: "
        f"{order.get('items', [])}"
    )


    template = load_prompt(
        "order_assistant_prompt.txt"
    )


    prompt = template.format(
        order_context=
            order_context,

        question=
            question,
    )


    ai_response = ask_ollama(
        prompt
    )


    if ai_response:
        return jsonify({
            "order_id":
                order_id,

            "answer":
                ai_response,

            "source":
                "ollama"
        }), 200


    fallback = (
        f"Order #{order['order_id']} "
        f"is currently "
        f"{order['status']}. "

        f"The order total is "
        f"${float(order['total_amount']):.2f}."
    )


    return jsonify({
        "order_id":
            order_id,

        "answer":
            fallback,

        "source":
            "fallback"
    }), 200


if __name__ == "__main__":
    print(
        "Order Backend API running on "
        "http://localhost:5004"
    )

    print(
        "Order Database API expected at "
        f"{DATABASE_URL}"
    )

    print(
        "Ollama expected at "
        f"{OLLAMA_URL}"
    )

    app.run(
        host="0.0.0.0",  # noqa: S104 - Docker must accept connections on all interfaces
        port=5004,
        debug=os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"
    )
