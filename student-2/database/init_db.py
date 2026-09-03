import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATABASE_NAME = os.path.join(DATA_DIR, "products.db")

os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    brand TEXT,
    status TEXT NOT NULL
);
""")

cursor.execute("DELETE FROM products")

products = [
    (1, "Air Max 270", "Shoes", "Comfortable lifestyle sneakers", 220.00, "Nike", "active"),
    (2, "Classic Hoodie", "Clothing", "Cotton everyday hoodie", 89.95, "Adidas", "active"),
    (3, "Classic Sneakers", "Shoes", "Casual everyday sneakers", 119.00, "Adidas", "active"),
    (4, "Running Shorts", "Clothing", "Lightweight running shorts", 49.99, "Nike", "active"),
    (5, "Suede Sneakers", "Shoes", "Premium suede sneakers", 150.00, "Puma", "active"),
    (6, "Sports Backpack", "Accessories", "Durable sports backpack", 79.99, "Nike", "active"),
    (7, "Training T-Shirt", "Clothing", "Breathable training t-shirt", 39.99, "Adidas", "active"),
    (8, "Running Cap", "Accessories", "Lightweight running cap", 29.99, "Nike", "active"),
    (9, "Track Pants", "Clothing", "Comfortable track pants", 59.99, "Adidas", "active"),
    (10, "Running Shoes", "Shoes", "High-performance running shoes", 199.99, "Nike", "active")
]

cursor.executemany(
    """
    INSERT INTO products (
    product_id, 
    name,
    category,
    description,
    price, 
    brand,
    status
    ) 
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    products
)

conn.commit()
conn.close()

print("Database initialised with 10 products.")