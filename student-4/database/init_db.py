import argparse
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("ORDERS_DB_PATH", os.path.join(os.path.dirname(__file__), "orders.db"))
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def initialize(db_path=None):
    """Create missing tables without replacing existing orders or items."""
    target_path = db_path or DB_PATH
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target_path) as connection:
        connection.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))


def seed(db_path=None, *, reset=False):
    """Add demo fixtures to an empty database; replacing data requires reset=True."""
    target_path = db_path or DB_PATH
    initialize(target_path)

    connection = sqlite3.connect(target_path)
    connection.execute("PRAGMA foreign_keys = ON")
    cursor = connection.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    if reset:
        cursor.execute("DELETE FROM order_items")
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders', 'order_items')")
    elif cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]:
        connection.close()
        raise ValueError("Database already contains orders; demo seed refused. Use --seed-demo --reset only for disposable data.")

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

    order_ids = []
    for order in orders:
        cursor.execute(
            "INSERT INTO orders (customer_id, total_amount, status) VALUES (?, ?, ?)", order
        )
        order_ids.append(cursor.lastrowid)

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
        [(order_ids[row[0] - 1], *row[1:]) for row in order_items],
    )

    connection.commit()
    connection.close()

    print(
        f"Seeded {target_path} with "
        f"{len(orders)} orders and {len(order_items)} order items."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize Orders safely or explicitly seed demo data")
    parser.add_argument("--seed-demo", action="store_true", help="Insert sample orders into an empty database")
    parser.add_argument("--reset", action="store_true", help="Delete existing orders before demo seeding")
    args = parser.parse_args()
    if args.reset and not args.seed_demo:
        parser.error("--reset requires --seed-demo")
    if args.seed_demo:
        seed(reset=args.reset)
    else:
        initialize()
        print("Orders schema ready; existing data preserved.")
