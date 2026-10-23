from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sqlite3
from contextlib import closing

app = Flask(__name__)
CORS(app)

DB_PATH = os.getenv("ORDERS_DB_PATH", os.path.join(os.path.dirname(__file__), "orders.db"))


def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "service": "order-database",
        "status": "ok"
    }), 200


@app.post("/orders/verified-purchase")
def verified_purchase():
    data = request.get_json(silent=True)
    if (not isinstance(data, dict) or any(type(data.get(key)) is not int or not 0 < data[key] <= 2147483647
                                         for key in ("customer_id", "product_id"))):
        return jsonify(error="Valid customer and product required."), 400
    try:
        with closing(get_db_connection()) as connection:
            row = connection.execute(
                "SELECT EXISTS(SELECT 1 FROM orders o JOIN order_items i ON i.order_id=o.order_id "
                "WHERE o.customer_id=? AND o.status='CONFIRMED' AND i.product_id=?)",
                (data["customer_id"], data["product_id"]),
            ).fetchone()
        return jsonify(verified_purchase=bool(row[0]))
    except sqlite3.Error:
        return jsonify(error="Purchase verification unavailable."), 503


@app.route("/orders", methods=["GET"])
def get_orders():
    customer_id = request.args.get("customer_id")

    connection = get_db_connection()

    if customer_id:
        rows = connection.execute(
            """
            SELECT *
            FROM orders
            WHERE customer_id = ?
            ORDER BY order_id DESC
            """,
            (customer_id,)
        ).fetchall()

    else:
        rows = connection.execute(
            """
            SELECT *
            FROM orders
            ORDER BY order_id DESC
            """
        ).fetchall()

    connection.close()

    return jsonify(
        [dict(row) for row in rows]
    ), 200

@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    connection = get_db_connection()

    order = connection.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,)
    ).fetchone()

    if not order:
        connection.close()
        return jsonify({"error": "Order not found"}), 404

    items = connection.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY order_item_id",
        (order_id,)
    ).fetchall()

    connection.close()

    result = dict(order)
    result["items"] = [dict(item) for item in items]

    return jsonify(result), 200


@app.route("/orders", methods=["POST"])
def create_order():
    data = request.json or {}

    customer_id = data.get("customer_id")
    items = data.get("items", [])

    if not customer_id:
        return jsonify({"error": "customer_id is required"}), 400

    if not items:
        return jsonify({"error": "At least one order item is required"}), 400

    total_amount = 0
    validated_items = []

    for item in items:
        product_id = item.get("product_id")
        quantity = item.get("quantity")
        unit_price = item.get("unit_price")

        if product_id is None or quantity is None or unit_price is None:
            return jsonify({
                "error": "Each item requires product_id, quantity and unit_price"
            }), 400

        try:
            quantity = int(quantity)
            unit_price = float(unit_price)
        except (TypeError, ValueError):
            return jsonify({
                "error": "quantity and unit_price must be numeric"
            }), 400

        if quantity <= 0:
            return jsonify({"error": "quantity must be greater than 0"}), 400

        if unit_price < 0:
            return jsonify({"error": "unit_price cannot be negative"}), 400

        product_name = item.get("product_name")
        if product_name is not None and (not isinstance(product_name, str) or not 0 < len(product_name.strip()) <= 120):
            return jsonify(error="Invalid product name."), 400
        subtotal = round(quantity * unit_price, 2)
        total_amount += subtotal

        validated_items.append({
            "product_id": product_id,
            "product_name": product_name.strip() if product_name is not None else None,
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal
        })

    total_amount = round(total_amount, 2)

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO orders (customer_id, total_amount, status)
            VALUES (?, ?, 'PENDING')
            """,
            (customer_id, total_amount)
        )

        order_id = cursor.lastrowid

        for item in validated_items:
            cursor.execute(
                """
                INSERT INTO order_items
                (order_id, product_id, product_name, quantity, unit_price, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    item["product_id"],
                    item["product_name"],
                    item["quantity"],
                    item["unit_price"],
                    item["subtotal"]
                )
            )

        connection.commit()

    except sqlite3.Error as error:
        connection.rollback()
        connection.close()

        return jsonify({
            "error": "Database error",
            "details": str(error)
        }), 500

    connection.close()

    return jsonify({
        "message": "Order created successfully",
        "order_id": order_id,
        "total_amount": total_amount,
        "status": "PENDING"
    }), 201


@app.route("/orders/<int:order_id>", methods=["PUT"])
def update_order(order_id):
    data = request.json or {}
    status = data.get("status")

    allowed_statuses = ["PENDING", "CONFIRMED", "CANCELLED"]

    if status not in allowed_statuses:
        return jsonify({
            "error": "status must be PENDING, CONFIRMED, or CANCELLED"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE orders
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
        """,
        (status, order_id)
    )

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    if not updated:
        return jsonify({"error": "Order not found"}), 404

    return jsonify({
        "message": "Order updated successfully",
        "order_id": order_id,
        "status": status
    }), 200


@app.route("/orders/<int:order_id>", methods=["DELETE"])
def cancel_order(order_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE orders
        SET status = 'CANCELLED',
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
        """,
        (order_id,)
    )

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    if not updated:
        return jsonify({"error": "Order not found"}), 404

    return jsonify({
        "message": "Order cancelled successfully",
        "order_id": order_id,
        "status": "CANCELLED"
    }), 200


@app.route("/orders/count", methods=["GET"])
def order_count():
    connection = get_db_connection()

    row = connection.execute(
        "SELECT COUNT(*) AS count FROM orders"
    ).fetchone()

    connection.close()

    return jsonify({
        "count": row["count"]
    }), 200


if __name__ == "__main__":
    from init_db import initialize

    initialize(DB_PATH)
    print("Order Database API running on http://localhost:6004")
    app.run(host="0.0.0.0", port=6004, debug=False)  # noqa: S104 - container ingress requires all interfaces
