from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "recommendations.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row):
    return dict(row) if row else None


def seed_if_empty():
    connection = get_db_connection()
    count = connection.execute("SELECT COUNT(*) AS count FROM customer_preferences").fetchone()["count"]
    connection.close()
    if count == 0:
        from init_db import seed
        seed(db_path=DB_PATH)
        print("Database was empty — seeded sample data.")


def ensure_database():
    if not os.path.exists(DB_PATH):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
            connection = sqlite3.connect(DB_PATH)
            connection.executescript(schema_file.read())
            connection.commit()
            connection.close()
    seed_if_empty()


# ── Customer preferences CRUD ──

@app.route("/preferences", methods=["GET"])
def list_preferences():
    connection = get_db_connection()
    rows = connection.execute("SELECT * FROM customer_preferences ORDER BY customer_id").fetchall()
    connection.close()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/preferences/<int:customer_id>", methods=["GET"])
def get_preferences(customer_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT * FROM customer_preferences WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    connection.close()
    if not row:
        return jsonify({"error": "Preferences not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/preferences", methods=["POST"])
def create_preferences():
    data = request.json or {}
    required = ["customer_id", "product_category_interests", "preferred_brands"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required fields"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """INSERT INTO customer_preferences
            (customer_id, product_category_interests, preferred_brands, price_range_min, price_range_max)
            VALUES (?, ?, ?, ?, ?)""",
            (
                data["customer_id"],
                data["product_category_interests"],
                data["preferred_brands"],
                data.get("price_range_min", 0),
                data.get("price_range_max", 500),
            ),
        )
        connection.commit()
        preference_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        connection.close()
        return jsonify({"error": "Preferences already exist for this customer"}), 409
    connection.close()
    return jsonify({"preference_id": preference_id}), 201


@app.route("/preferences/<int:customer_id>", methods=["PUT"])
def update_preferences(customer_id):
    data = request.json or {}
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE customer_preferences
        SET product_category_interests = ?,
            preferred_brands = ?,
            price_range_min = ?,
            price_range_max = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE customer_id = ?""",
        (
            data.get("product_category_interests", ""),
            data.get("preferred_brands", ""),
            data.get("price_range_min", 0),
            data.get("price_range_max", 500),
            customer_id,
        ),
    )
    connection.commit()
    updated = cursor.rowcount
    connection.close()
    if not updated:
        return jsonify({"error": "Preferences not found"}), 404
    return jsonify({"updated": customer_id})


@app.route("/preferences/<int:customer_id>", methods=["DELETE"])
def delete_preferences(customer_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM customer_preferences WHERE customer_id = ?", (customer_id,))
    connection.commit()
    deleted = cursor.rowcount
    connection.close()
    if not deleted:
        return jsonify({"error": "Preferences not found"}), 404
    return jsonify({"deleted": customer_id})


# ── Browsing history CRUD ──

@app.route("/browsing-history", methods=["GET"])
def list_browsing_history():
    customer_id = request.args.get("customer_id")
    connection = get_db_connection()
    if customer_id:
        rows = connection.execute(
            "SELECT * FROM browsing_history WHERE customer_id = ? ORDER BY viewed_at DESC",
            (customer_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM browsing_history ORDER BY viewed_at DESC"
        ).fetchall()
    connection.close()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/browsing-history/<int:history_id>", methods=["GET"])
def get_browsing_entry(history_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT * FROM browsing_history WHERE history_id = ?", (history_id,)
    ).fetchone()
    connection.close()
    if not row:
        return jsonify({"error": "History entry not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/browsing-history", methods=["POST"])
def create_browsing_entry():
    data = request.json or {}
    if "customer_id" not in data or "product_id" not in data:
        return jsonify({"error": "customer_id and product_id are required"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO browsing_history (customer_id, product_id, time_spent)
        VALUES (?, ?, ?)""",
        (data["customer_id"], data["product_id"], data.get("time_spent", 0)),
    )
    connection.commit()
    history_id = cursor.lastrowid
    connection.close()
    return jsonify({"history_id": history_id}), 201


@app.route("/browsing-history/<int:history_id>", methods=["PUT"])
def update_browsing_entry(history_id):
    data = request.json or {}
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE browsing_history
        SET product_id = ?, time_spent = ?, viewed_at = CURRENT_TIMESTAMP
        WHERE history_id = ?""",
        (data.get("product_id"), data.get("time_spent", 0), history_id),
    )
    connection.commit()
    updated = cursor.rowcount
    connection.close()
    if not updated:
        return jsonify({"error": "History entry not found"}), 404
    return jsonify({"updated": history_id})


@app.route("/browsing-history/<int:history_id>", methods=["DELETE"])
def delete_browsing_entry(history_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM browsing_history WHERE history_id = ?", (history_id,))
    connection.commit()
    deleted = cursor.rowcount
    connection.close()
    if not deleted:
        return jsonify({"error": "History entry not found"}), 404
    return jsonify({"deleted": history_id})


# ── Recommendations ──

@app.route("/recommendations", methods=["GET"])
def list_recommendations():
    customer_id = request.args.get("customer_id")
    product_id = request.args.get("product_id")
    connection = get_db_connection()

    if customer_id:
        rows = connection.execute(
            """SELECT * FROM recommendations
            WHERE customer_id = ? ORDER BY recommendation_score DESC, created_at DESC""",
            (customer_id,),
        ).fetchall()
    elif product_id:
        rows = connection.execute(
            """SELECT * FROM recommendations
            WHERE recommended_product_id = ? ORDER BY created_at DESC""",
            (product_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM recommendations ORDER BY created_at DESC"
        ).fetchall()

    connection.close()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/recommendations/<int:recommendation_id>", methods=["GET"])
def get_recommendation(recommendation_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
    ).fetchone()
    connection.close()
    if not row:
        return jsonify({"error": "Recommendation not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/recommendations", methods=["POST"])
def create_recommendation():
    data = request.json or {}
    required = ["customer_id", "recommended_product_id", "recommendation_score"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required fields"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO recommendations
        (customer_id, recommended_product_id, recommendation_score, explanation)
        VALUES (?, ?, ?, ?)""",
        (
            data["customer_id"],
            data["recommended_product_id"],
            data["recommendation_score"],
            data.get("explanation", ""),
        ),
    )
    connection.commit()
    recommendation_id = cursor.lastrowid
    connection.close()
    return jsonify({"recommendation_id": recommendation_id}), 201


@app.route("/recommendations/<int:recommendation_id>", methods=["PUT"])
def update_recommendation(recommendation_id):
    data = request.json or {}
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE recommendations
        SET recommendation_score = ?, explanation = ?
        WHERE recommendation_id = ?""",
        (
            data.get("recommendation_score"),
            data.get("explanation", ""),
            recommendation_id,
        ),
    )
    connection.commit()
    updated = cursor.rowcount
    connection.close()
    if not updated:
        return jsonify({"error": "Recommendation not found"}), 404
    return jsonify({"updated": recommendation_id})


@app.route("/recommendations/<int:recommendation_id>", methods=["DELETE"])
def delete_recommendation(recommendation_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM recommendation_feedback WHERE recommendation_id = ?", (recommendation_id,)
    )
    cursor.execute(
        "DELETE FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
    )
    connection.commit()
    deleted = cursor.rowcount
    connection.close()
    if not deleted:
        return jsonify({"error": "Recommendation not found"}), 404
    return jsonify({"deleted": recommendation_id})


@app.route("/recommendations/customer/<int:customer_id>", methods=["DELETE"])
def clear_customer_recommendations(customer_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    rec_ids = [
        row["recommendation_id"]
        for row in cursor.execute(
            "SELECT recommendation_id FROM recommendations WHERE customer_id = ?", (customer_id,)
        ).fetchall()
    ]
    for rec_id in rec_ids:
        cursor.execute(
            "DELETE FROM recommendation_feedback WHERE recommendation_id = ?", (rec_id,)
        )
    cursor.execute("DELETE FROM recommendations WHERE customer_id = ?", (customer_id,))
    connection.commit()
    connection.close()
    return jsonify({"cleared_for_customer": customer_id})


# ── Recommendation feedback ──

@app.route("/recommendation-feedback", methods=["GET"])
def list_feedback():
    recommendation_id = request.args.get("recommendation_id")
    connection = get_db_connection()
    if recommendation_id:
        rows = connection.execute(
            "SELECT * FROM recommendation_feedback WHERE recommendation_id = ? ORDER BY created_at DESC",
            (recommendation_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM recommendation_feedback ORDER BY created_at DESC"
        ).fetchall()
    connection.close()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/recommendation-feedback", methods=["POST"])
def create_feedback():
    data = request.json or {}
    if "recommendation_id" not in data or "customer_feedback_rating" not in data:
        return jsonify({"error": "recommendation_id and customer_feedback_rating are required"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO recommendation_feedback
        (recommendation_id, customer_feedback_rating, was_purchased, helpful)
        VALUES (?, ?, ?, ?)""",
        (
            data["recommendation_id"],
            data["customer_feedback_rating"],
            1 if data.get("was_purchased") else 0,
            1 if data.get("helpful", True) else 0,
        ),
    )
    connection.commit()
    feedback_id = cursor.lastrowid
    connection.close()
    return jsonify({"feedback_id": feedback_id}), 201


@app.route("/recommendation-feedback/<int:feedback_id>", methods=["PUT"])
def update_feedback(feedback_id):
    data = request.json or {}
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE recommendation_feedback
        SET customer_feedback_rating = ?, was_purchased = ?, helpful = ?
        WHERE feedback_id = ?""",
        (
            data.get("customer_feedback_rating"),
            1 if data.get("was_purchased") else 0,
            1 if data.get("helpful", True) else 0,
            feedback_id,
        ),
    )
    connection.commit()
    updated = cursor.rowcount
    connection.close()
    if not updated:
        return jsonify({"error": "Feedback not found"}), 404
    return jsonify({"updated": feedback_id})


@app.route("/recommendation-feedback/<int:feedback_id>", methods=["DELETE"])
def delete_feedback(feedback_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM recommendation_feedback WHERE feedback_id = ?", (feedback_id,)
    )
    connection.commit()
    deleted = cursor.rowcount
    connection.close()
    if not deleted:
        return jsonify({"error": "Feedback not found"}), 404
    return jsonify({"deleted": feedback_id})


# ── Metrics ──

@app.route("/stats/metrics", methods=["GET"])
def recommendation_metrics():
    connection = get_db_connection()
    total_recommendations = connection.execute(
        "SELECT COUNT(*) AS count FROM recommendations"
    ).fetchone()["count"]
    total_feedback = connection.execute(
        "SELECT COUNT(*) AS count FROM recommendation_feedback"
    ).fetchone()["count"]
    avg_rating_row = connection.execute(
        "SELECT AVG(customer_feedback_rating) AS avg_rating FROM recommendation_feedback"
    ).fetchone()
    helpful_count = connection.execute(
        "SELECT COUNT(*) AS count FROM recommendation_feedback WHERE helpful = 1"
    ).fetchone()["count"]
    purchase_count = connection.execute(
        "SELECT COUNT(*) AS count FROM recommendation_feedback WHERE was_purchased = 1"
    ).fetchone()["count"]
    connection.close()

    avg_rating = round(avg_rating_row["avg_rating"] or 0, 2)
    helpful_rate = round((helpful_count / total_feedback) * 100, 1) if total_feedback else 0

    return jsonify({
        "total_recommendations": total_recommendations,
        "total_feedback": total_feedback,
        "average_feedback_rating": avg_rating,
        "helpful_rate_percent": helpful_rate,
        "purchase_conversion_count": purchase_count,
    })


if __name__ == "__main__":
    ensure_database()
    print("Database API running on http://localhost:6005")
    app.run(host="0.0.0.0", port=6005, debug=True)
