"""Post-commit checks for two distinct Student 2 backend endpoints."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("student2_backend_app", BACKEND / "app.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def test_get_product_returns_database_result():
    product = {"product_id": 103, "name": "Test Sneaker", "price": 99}
    with patch.object(backend.requests, "get", return_value=Mock(status_code=200, **{"json.return_value": product})) as get:
        response = backend.app.test_client().get("/products/103")
    assert response.status_code == 200
    assert response.get_json() == product
    get.assert_called_once_with(f"{backend.DATABASE_URL}/products/103", timeout=5)


def test_get_product_preserves_not_found_status():
    with patch.object(backend.requests, "get", return_value=Mock(status_code=404, **{"json.return_value": {"error": "Product not found"}})):
        response = backend.app.test_client().get("/products/999999")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Product not found"}


def test_create_product_forwards_request_and_returns_created_id():
    product = {"name": "Test Sneaker", "category": "Shoes", "price": 99, "status": "active"}
    with patch.object(backend.requests, "post", return_value=Mock(status_code=201, **{"json.return_value": {"product_id": 103, "message": "Product created"}})) as post:
        response = backend.app.test_client().post("/products", json=product)
    assert response.status_code == 201
    assert response.get_json()["product_id"] == 103
    post.assert_called_once_with(f"{backend.DATABASE_URL}/products", json=product, timeout=5)
