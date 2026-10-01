import os

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from prompt_loader import load_prompt


app = Flask(__name__)
CORS(app)


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


@app.route(
    "/api/orders",
    methods=["GET"]
)
def get_orders():
    customer_id = request.args.get("customer_id")

    path = "/orders"

    if customer_id:
        path += f"?customer_id={customer_id}"

    response = db_get(path)

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/api/orders/<int:order_id>",
    methods=["GET"]
)
def get_order(order_id):
    response = db_get(
        f"/orders/{order_id}"
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/api/orders",
    methods=["POST"]
)
def create_order():
    data = request.json or {}

    response = db_post(
        "/orders",
        data
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/api/orders/<int:order_id>",
    methods=["PUT"]
)
def update_order(order_id):
    data = request.json or {}

    response = db_put(
        f"/orders/{order_id}",
        data
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/api/orders/<int:order_id>",
    methods=["DELETE"]
)
def cancel_order(order_id):
    response = db_delete(
        f"/orders/{order_id}"
    )

    return jsonify(
        response.json()
    ), response.status_code


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


    db_response = db_get(
        f"/orders/{order_id}"
    )


    if (
        db_response.status_code
        != 200
    ):
        return jsonify(
            db_response.json()
        ), db_response.status_code


    order = db_response.json()


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
        host="0.0.0.0",
        port=5004,
        debug=True
    )