from flask import Flask, jsonify, request
import sqlite3
import os

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'reviews.db')

def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

@app.route('/reviews', methods=['GET'])
def get_all_reviews():
    connection = get_db_connection()
    rows = connection.execute('SELECT * FROM reviews ORDER BY created_at DESC').fetchall()
    connection.close()
    return jsonify([dict(row) for row in rows])

@app.route('/reviews/<int:product_id>', methods=['GET'])
def get_review_for_product(product_id):
    connection = get_db_connection()
    rows = connection.execute(
        'SELECT * FROM reviews WHERE product_id = ? ORDER BY created_at DESC', (product_id,)
    ).fetchall()
    connection.close()
    return jsonify([dict(row) for row in rows])

@app.route('/reviews', methods=['POST'])
def create_review():
    data = request.json
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO reviews (product_id, customer_id, rating, comment, sentiment_score, is_flagged) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (
            data['product_id'], 
            data['customer_id'], 
            data['rating'], 
            data['comment'], 
            data['sentiment_score'], 
            data['is_flagged']
        )
    )
    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return jsonify({'review_id': new_id}), 201

@app.route('/reviews/<int:review_id>', methods=['PUT'])
def update_review(review_id):
    data = request.json
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE reviews 
        SET rating = ?, comment = ?, is_flagged = ?
        WHERE review_id = ?""",
        (
            data['rating'], 
            data.get('comment', ''),
            data.get('is_flagged', False),
            review_id
        )
    )
    connection.commit()
    connection.close()
    return jsonify({"updated": review_id})

@app.route('/reviews/<int:review_id>', methods=['DELETE'])
def delete_review(review_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('DELETE FROM reviews WHERE review_id = ?', (review_id,))
    connection.commit()
    connection.close()
    return jsonify({"deleted": review_id})

@app.route('/reviews/summary/<int:product_id>', methods=['GET'])
def get_review_summary(product_id):
    connection = get_db_connection()
    row = connection.execute(
        'SELECT * FROM review_summaries WHERE product_id = ?', (product_id,)
    ).fetchone()
    connection.close()
    if row:
        return jsonify(dict(row))
    else:
        return jsonify({"error": "Summary not found"}), 404

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=6001, debug=True)