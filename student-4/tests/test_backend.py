import importlib.util
import os
import sys
from unittest.mock import patch, Mock

BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "backend"
)

sys.path.insert(0, os.path.abspath(BACKEND_DIR))

def load_backend():
    spec = importlib.util.spec_from_file_location(
        "student4_backend",
        os.path.join(BACKEND_DIR, "app.py"),
    )

    module = importlib.util.module_from_spec(spec)
    sys.modules["student4_backend"] = module

    spec.loader.exec_module(module)

    module.app.config["TESTING"] = True

    return module


def test_backend_health():
    backend = load_backend()

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "service": "order-database",
        "status": "ok"
    }

    with patch.object(
        backend,
        "db_get",
        return_value=mock_response
    ):
        with backend.app.test_client() as client:

            response = client.get("/api/health")

            assert response.status_code == 200

            data = response.get_json()

            assert data["status"] == "ok"
            assert data["database_connected"] is True
            assert data["backend_port"] == 5004
            assert data["database_port"] == 6004


def test_order_assistant_requires_question():
    backend = load_backend()

    with backend.app.test_client() as client:

        response = client.post(
            "/api/order-assistant",
            json={
                "order_id": 1
            }
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "question is required"


def test_order_assistant_requires_order_id():
    backend = load_backend()

    with backend.app.test_client() as client:

        response = client.post(
            "/api/order-assistant",
            json={
                "question": "Where is my order?"
            }
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "order_id is required"


def test_order_assistant_uses_ollama():
    backend = load_backend()

    mock_db = Mock()
    mock_db.status_code = 200
    mock_db.json.return_value = {
        "order_id": 1,
        "customer_id": 1,
        "status": "CONFIRMED",
        "total_amount": 149.99,
        "order_date": "2026-09-03 13:27:02",
        "items": [
            {
                "product_id": 101,
                "quantity": 1,
                "unit_price": 149.99,
                "subtotal": 149.99
            }
        ]
    }

    with patch.object(
        backend,
        "db_get",
        return_value=mock_db
    ):
        with patch.object(
            backend,
            "ask_ollama",
            return_value="Order #1 is confirmed."
        ):
            with backend.app.test_client() as client:

                response = client.post(
                    "/api/order-assistant",
                    json={
                        "order_id": 1,
                        "question": "What is the status?"
                    }
                )

                assert response.status_code == 200

                data = response.get_json()

                assert data["source"] == "ollama"
                assert "confirmed" in data["answer"].lower()


def test_order_assistant_fallback():
    backend = load_backend()

    mock_db = Mock()
    mock_db.status_code = 200
    mock_db.json.return_value = {
        "order_id": 1,
        "customer_id": 1,
        "status": "CONFIRMED",
        "total_amount": 149.99,
        "order_date": "2026-09-03 13:27:02",
        "items": []
    }

    with patch.object(
        backend,
        "db_get",
        return_value=mock_db
    ):
        with patch.object(
            backend,
            "ask_ollama",
            return_value=None
        ):
            with backend.app.test_client() as client:

                response = client.post(
                    "/api/order-assistant",
                    json={
                        "order_id": 1,
                        "question": "What is the status?"
                    }
                )

                assert response.status_code == 200

                data = response.get_json()

                assert data["source"] == "fallback"
                assert "CONFIRMED" in data["answer"]