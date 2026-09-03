import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest

DATABASE_DIR = os.path.join(os.path.dirname(__file__), "..", "database")


def load_database_app():
    spec = importlib.util.spec_from_file_location(
        "student5_database",
        os.path.join(DATABASE_DIR, "app.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["student5_database"] = module
    spec.loader.exec_module(module)
    return module


class DatabaseApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        self.db_app = load_database_app()
        self.db_app.DB_PATH = self.temp_db.name

        with open(self.db_app.SCHEMA_PATH, encoding="utf-8") as schema_file:
            connection = sqlite3.connect(self.temp_db.name)
            connection.executescript(schema_file.read())
            connection.commit()
            connection.close()

        self.client = self.db_app.app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_preferences_crud(self):
        create = self.client.post(
            "/preferences",
            json={
                "customer_id": 99,
                "product_category_interests": "street",
                "preferred_brands": "Nike",
                "price_range_min": 50,
                "price_range_max": 150,
            },
        )
        self.assertEqual(create.status_code, 201)

        get = self.client.get("/preferences/99")
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.json["preferred_brands"], "Nike")

    def test_browsing_history_create(self):
        response = self.client.post(
            "/browsing-history",
            json={"customer_id": 1, "product_id": 101, "time_spent": 45},
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("history_id", response.json)

    def test_metrics_endpoint(self):
        response = self.client.get("/stats/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("total_recommendations", response.json)


if __name__ == "__main__":
    unittest.main()
