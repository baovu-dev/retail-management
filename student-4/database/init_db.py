import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def seed(db_path=None):
    target_path = db_path or DB_PATH

    connection = sqlite3.connect(target_path)
    cursor = connection.cursor()

    # Create database tables from schema.sql
    with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
        cursor.executescript(schema_file.read())

    # Clear existing data so the seed can be run repeatedly
    cursor.execute("DELETE FROM order_items")
    cursor.execute("DELETE FROM orders")

    # Sample orders for Release 0
    orders = [
        (1, 149.99, "CONFIRMED"),
        (2, 179.98, "PENDING"),
        (3, 79.99, "CONFIRMED"),
        (1, 110.00, "PENDING"),
        (2, 119.99, "CANCELLED"),
        (3, 129.99, "CONFIRMED"),
        (1, 210.00, "CONFIRMED"),
        (2, 99.99, "PENDING"),
        (3, 239.98, "CONFIRMED"),
        (1, 259.98, "PENDING"),
    ]

    cursor.executemany(
        """
        INSERT INTO orders (customer_id, total_amount, status)
        VALUES (?, ?, ?)
        """,
        orders,
    )

    # At least one item for every sample order
    order_items = [
        (1, 101, 1, 149.99, 149.99),
        (2, 102, 2, 89.99, 179.98),
        (3, 103, 1, 79.99, 79.99),
        (4, 104, 1, 110.00, 110.00),
        (5, 105, 1, 119.99, 119.99),
        (6, 106, 1, 129.99, 129.99),
        (7, 107, 1, 210.00, 210.00),
        (8, 108, 1, 99.99, 99.99),
        (9, 105, 2, 119.99, 239.98),
        (10, 106, 2, 129.99, 259.98),
    ]

    cursor.executemany(
        """
        INSERT INTO order_items
        (order_id, product_id, quantity, unit_price, subtotal)
        VALUES (?, ?, ?, ?, ?)
        """,
        order_items,
    )

    connection.commit()
    connection.close()

    print(
        f"Seeded {target_path} with "
        f"{len(orders)} orders and {len(order_items)} order items."
    )


if __name__ == "__main__":
    seed()