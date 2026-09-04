import importlib.util
import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_DIR)


def load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


backend = load_module("student5_backend", os.path.join(BACKEND_DIR, "app.py"))
catalog = load_module("student5_catalog", os.path.join(BACKEND_DIR, "catalog.py"))


class RecommendationLogicTests(unittest.TestCase):
    def test_infer_everyday_nike_budget(self):
        prefs = backend.infer_chat_preferences("everyday Nike sneakers under 120")
        self.assertIn("everyday", prefs["product_category_interests"])
        self.assertIn("Nike", prefs["preferred_brands"])
        self.assertEqual(prefs["price_range_max"], 120.0)

    def test_infer_basketball_jordan(self):
        prefs = backend.infer_chat_preferences("basketball jordan shoes")
        self.assertIn("basketball", prefs["product_category_interests"])
        self.assertIn("Jordan", prefs["preferred_brands"])

    def test_chat_score_boosts_mentioned_product(self):
        product = catalog.get_product(108)
        score = backend.chat_product_score(
            product,
            "everyday nike under 120",
            "Try the Nike Air Force 1 Low for casual wear.",
        )
        self.assertGreater(score, 0.5)

    def test_chat_explanation_includes_product_name(self):
        product = catalog.get_product(108)
        explanation = backend.build_chat_explanation(
            product,
            "everyday sneakers",
            backend.infer_chat_preferences("everyday sneakers"),
        )
        self.assertIn("Air Force 1", explanation)

    def test_budget_filter_excludes_expensive_shoes(self):
        prefs = backend.infer_chat_preferences("shoes under 120")
        self.assertTrue(prefs["budget_specified"])
        self.assertEqual(prefs["price_range_max"], 120.0)
        jordan1 = catalog.get_product(101)
        af1 = catalog.get_product(108)
        self.assertFalse(backend.product_matches_budget(jordan1, prefs))
        self.assertTrue(backend.product_matches_budget(af1, prefs))

    def test_build_recommendations_respects_under_120(self):
        saved = {}

        def fake_put(path, payload):
            saved.update(payload)

        def fake_get(path, **params):
            class R:
                status_code = 200

                def json(self):
                    if path == "/browsing-history":
                        return []
                    return {}

            return R()

        def fake_delete(path):
            class R:
                status_code = 200
            return R()

        def fake_post(path, payload):
            class R:
                status_code = 201

                def json(self):
                    return {"recommendation_id": 1}

            return R()

        backend.db_put = fake_put
        backend.db_get = fake_get
        backend.db_delete = fake_delete
        backend.db_post = fake_post
        backend.get_customer_context = lambda cid: ({}, [], set())

        recs = backend.build_recommendations_from_chat(1, "shoes under 120", "")
        self.assertTrue(recs)
        for item in recs:
            self.assertLessEqual(item["product"]["price"], 120)

    def test_similar_products_excludes_self(self):
        similar = backend.similar_products_for_product(108)
        ids = [item["product"]["product_id"] for item in similar]
        self.assertNotIn(108, ids)
        self.assertGreaterEqual(len(similar), 1)

    def test_catalog_has_products(self):
        self.assertGreaterEqual(len(catalog.get_all_products()), 6)


if __name__ == "__main__":
    unittest.main()
