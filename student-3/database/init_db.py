import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'customer.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

def seed():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    with open(SCHEMA_PATH, 'r') as f:
        cursor.executescript(f.read())

        cursor.execute("DELETE FROM customer")

        sample_customers = [
            ("Ahmad", "Abdi", "0489543890", "ahmad.abdi@gmail.com", "Active"),
            ("Mohammed", "Ali", "0454789423", "mohammed.ali@gmail.com", "Active"),
            ("Cristiano", "Ronaldo", "047982344", "ronaldono2@gmail.com", "Active"),
            ("Lionel", "Messi", "0478453789", "messino1@gmail.com", "Active"),
            ("Sabrina", "Carpenter", "048923789", "sabrinacarpenter@gmail.com", "Active"),
            ("Barrack", "Obama", "047893212", "obama@gmail.com", "Active"),
            ("Joe", "Mama", "047812393", "joe.mama@gmail.com", "Inactive"),
            ("Taylor", "Swift", "047234233", "swiftie@gmail.com", "Active"),
            ("Mike", "Tyson", "0478234789", "mike.tyson@gmail.com", "Inactive"),
            ("Walter", "White", "0478234789", "walter.white@gmail.com", "Inactive")

        ]

        cursor.executemany(
            """
            INSERT INTO customer
            (first_name, last_name, phone, email, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            sample_customers
        )

        connection.commit()
        connection.close()

        print(f"Seeded {DB_PATH} with {len(sample_customers)} customers.")

if __name__ == "__main__":
    seed()