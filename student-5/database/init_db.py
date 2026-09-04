import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "recommendations.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def seed(db_path=None):
    target_path = db_path or DB_PATH
    connection = sqlite3.connect(target_path)
    cursor = connection.cursor()

    with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
        cursor.executescript(schema_file.read())

    cursor.execute("DELETE FROM recommendation_feedback")
    cursor.execute("DELETE FROM recommendations")
    cursor.execute("DELETE FROM browsing_history")
    cursor.execute("DELETE FROM customer_preferences")

    preferences = [
        (1, "basketball,street", "Nike,Jordan", 80, 250),
        (2, "everyday,running", "Adidas,New Balance", 50, 150),
        (3, "street,lifestyle", "Puma,Off White", 100, 300),
    ]
    cursor.executemany(
        """INSERT INTO customer_preferences
        (customer_id, product_category_interests, preferred_brands, price_range_min, price_range_max)
        VALUES (?, ?, ?, ?, ?)""",
        preferences,
    )

    browsing = [
        (1, 101, 120),
        (1, 102, 85),
        (1, 105, 200),
        (2, 103, 60),
        (2, 104, 90),
        (2, 106, 45),
        (3, 105, 150),
        (3, 107, 180),
        (3, 108, 95),
        (1, 103, 30),
        (2, 101, 75),
    ]
    cursor.executemany(
        """INSERT INTO browsing_history (customer_id, product_id, time_spent)
        VALUES (?, ?, ?)""",
        browsing,
    )

    recommendations = [
        # Intentionally empty — recommendations are generated via chat at runtime.
    ]
    cursor.executemany(
        """INSERT INTO recommendations
        (customer_id, recommended_product_id, recommendation_score, explanation)
        VALUES (?, ?, ?, ?)""",
        recommendations,
    )

    feedback = [
        # Intentionally empty — feedback is submitted from the frontend carousel.
    ]
    cursor.executemany(
        """INSERT INTO recommendation_feedback
        (recommendation_id, customer_feedback_rating, was_purchased, helpful)
        VALUES (?, ?, ?, ?)""",
        feedback,
    )

    connection.commit()
    connection.close()
    print(
        f"Seeded {DB_PATH} with {len(preferences)} preferences, "
        f"{len(browsing)} history entries. Recommendations start empty (chat-driven)."
    )


if __name__ == "__main__":
    seed()
