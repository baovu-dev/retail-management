from flask import Flask, jsonify, request
import sqlite3
import os

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATABASE_NAME = os.path.join(DATA_DIR, "products.db")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return jsonify([dict(product) for product in products])

@app.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    conn = get_db_connection()
    product = conn.execute(
        "SELECT * FROM products WHERE product_id = ?", 
        (product_id,)
    ).fetchone()
    conn.close()

    
    if product is None:
        return jsonify({"error": "Product not found"}), 404

    return jsonify(dict(product))

@app.route("/products", methods=["POST"])
def create_product():
    data = request.get_json()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO products (
            name, 
            category, 
            description, 
            price, 
            brand, 
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            data["name"], 
            data["category"], 
            data.get("description", ""), 
            data["price"], 
            data.get("brand", ""),
            data["status"]
        )
    )

    conn.commit()
    product_id = cursor.lastrowid
    conn.close()

    return jsonify({
        "message": "Product created",
        "product_id":  product_id
    }), 201

@app.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    data = request.get_json()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE products
        SET name = ?, 
            category = ?, 
            description = ?, 
            price = ?, 
            brand = ?, 
            status = ?
        WHERE product_id = ?
        """,
        (
            data["name"], 
            data["category"], 
            data.get("description", ""), 
            data["price"], 
            data.get("brand", ""),
            data["status"],
            product_id
        )
    )

    conn.commit()

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    conn.close()

    return jsonify({"message": "Product updated"})

@app.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM products WHERE product_id = ?", 
        (product_id,)
    )

    conn.commit()

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    conn.close()

    return jsonify({"message": "Product deleted"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=6002, debug=True)

