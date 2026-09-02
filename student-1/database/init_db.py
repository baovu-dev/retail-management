import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'reviews.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

def seed():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    with open(SCHEMA_PATH, 'r') as f:
        cursor.executescript(f.read())

    cursor.execute("DELETE FROM reviews")  # Clear existing data
    cursor.execute("DELETE FROM review_summaries") 

    sample_reviews = [
        (101, 1, 5, "Great quality, fast shipping!", 0.9, 0),
        (101, 2, 3, "Decent but overpriced.", 0.1, 0),
        (102, 1, 4, "Works as expected.", 0.5, 0),
        (102, 3, 2, "Broke after a week.", -0.7, 0),
        (103, 4, 5, "Exceeded my expectations!", 0.95, 0),
        (103, 2, 1, "Terrible, do not buy.", -0.9, 1),
        (104, 5, 4, "Solid value for money.", 0.6, 0),
        (104, 1, 3, "It's okay, nothing special.", 0.0, 0),
        (105, 3, 5, "Amazing customer service too.", 0.85, 0),
        (105, 4, 4, "Would recommend to a friend.", 0.7, 0),
        (106, 2, 2, "Not what I expected from the photos.", -0.4, 0),
    ]

    cursor.executemany(
        """INSERT INTO reviews (product_id, customer_id, rating, comment, sentiment_score, is_flagged)
        VALUES (?, ?, ?, ?, ?, ?)""",
        sample_reviews
    )

    sample_summaries = [
        (101, "Customers generally like the quality, though some feel it's overpriced."),
        (102, "Mixed reviews - some praise durability, others report it breaking quickly."),
        (103, "Highly polarized: either loved or hated by customers."),
        (104, "Considered solid value for money by most reviewers."),
        (105, "Consistently positive feedback, including praise for customer service."),
    ]

    cursor.executemany(
        """INSERT INTO review_summaries (product_id, generated_summary) 
        VALUES (?, ?)""", 
        sample_summaries
    )

    connection.commit()
    connection.close()
    print(f"Seeded {DB_PATH} with {len(sample_reviews)} reviews and {len(sample_summaries)} summaries.")

if __name__ == "__main__":
    seed()
