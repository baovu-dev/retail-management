from flask import Flask, jsonify, request
import sqlite3
import os

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'customer.db')

def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

@app.route('/customers', methods=['GET'])
def get_all_customers():
    connection = get_db_connection()

    rows = connection.execute(
        'SELECT * FROM customer ORDER BY customer_id'
    ).fetchall()

    connection.close()

    return jsonify([dict(row) for row in rows])

@app.route('/customers/<int:customer_id>', methods=['GET'])
def get_customer(customer_id):
    connection = get_db_connection()

    customer = connection.execute(
        'SELECT * FROM customer WHERE customer_id = ?',
        (customer_id,)
    ).fetchone()

    connection.close()

    if customer is None:
        return jsonify({'error': 'Customer not found'}), 404

    return jsonify(dict(customer))

@app.route('/customers', methods=['POST'])
def create_customer():
    data = request.json

    if not data.get('first_name') or not data.get('last_name') or not data.get('email'):
        return jsonify({'error': 'First name, last name and email are required'}), 400

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO customer
            (first_name, last_name, phone, email, status)
            VALUES (?, ?, ?, ?, ?)
            """,
        (
            data['first_name'],
            data['last_name'],
            data.get('phone'),
            data['email'],
            data.get('status', 'Active')
        )
    )

        connection.commit()

        new_id = cursor.lastrowid

        connection.close()

        return jsonify({'customer_id': new_id}), 201

    except sqlite3.IntegrityError:
        connection.close()

        return jsonify({'error': 'Email already exists'}), 400

@app.route('/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    data = request.json

    connection = get_db_connection()

    customer = connection.execute(
        'SELECT * FROM customer WHERE customer_id = ?',
        (customer_id,)
    ).fetchone()

    if customer is None:
        connection.close()
        return jsonify({'error': 'Cutsomer not found'}), 404

    try:
        connection.execute(
            """
            UPDATE customer
            SET first_name = ?,
                last_name = ?,
                phone = ?,
                email = ?,
                status = ?
            WHERE customer_id = ?
            """,
            (
                data.get('first_name', customer['first_name']),
                data.get('last_name', customer['last_name']),
                data.get('phone', customer['phone']),
                data.get('email', customer['email']),
                data.get('status', customer['status']),
                customer_id
            )
        )

        connection.commit()
        connection.close()

        return jsonify({'message': 'Customer updated successfully'})

    except sqlite3.IntegrityError:
        connection.close()
        return jsonify({'error': 'Email already exists'}), 400

@app.route('/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    connection = get_db_connection()

    customer = connection.execute(
        'SELECT * FROM customer WHERE customer_id = ?',
        (customer_id,)
    ).fetchone()

    if customer is None:
        connection.close()
        return jsonify({'error': 'Customer not found'}), 404

    connection.execute(
        'DELETE FROM customer WHERE customer_id = ?',
        (customer_id,)
    )

    connection.commit()
    connection.close()

    return jsonify({'message': 'Customer deleted successfully'})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6003, debug=True)