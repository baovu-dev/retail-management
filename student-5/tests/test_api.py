import importlib.util
import os
import sqlite3
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
DATABASE_DIR = os.path.join(os.path.dirname(__file__), "..", "database")


def load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def backend_client():
    backend = load_module("student5_backend_api", os.path.join(BACKEND_DIR, "app.py"))
    backend.app.config["TESTING"] = True
    with backend.app.test_client() as client:
        yield client


@pytest.fixture
def frontend_client():
    frontend = load_module("student5_frontend_api", os.path.join(FRONTEND_DIR, "app.py"))
    frontend.app.config["TESTING"] = True
    with frontend.app.test_client() as client:
        yield client


@pytest.fixture
def database_client():
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db.close()

    db_app = load_module("student5_database_api", os.path.join(DATABASE_DIR, "app.py"))
    db_app.DB_PATH = temp_db.name

    with open(db_app.SCHEMA_PATH, encoding="utf-8") as schema_file:
        connection = sqlite3.connect(temp_db.name)
        connection.executescript(schema_file.read())
        connection.commit()
        connection.close()

    db_app.app.config["TESTING"] = True
    with db_app.app.test_client() as client:
        yield client

    if os.path.exists(temp_db.name):
        os.unlink(temp_db.name)


def test_backend_lists_products(backend_client):
    response = backend_client.get("/api/products")
    assert response.status_code == 200
    assert len(response.get_json()) >= 6


def test_backend_product_detail(backend_client):
    response = backend_client.get("/api/products/108")
    assert response.status_code == 200
    assert response.get_json()["name"] == "Nike Air Force 1 Low"


def test_backend_similar_products(backend_client):
    response = backend_client.get("/api/recommendations/product/108")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_backend_health_reports_ports(backend_client):
    response = backend_client.get("/api/health")
    assert response.status_code in (200, 503)
    payload = response.get_json()
    assert payload["frontend_port"] == 3005
    assert payload["backend_port"] == 5005
    assert payload["database_port"] == 6005


def test_backend_chat_requires_message(backend_client):
    response = backend_client.post("/api/chat", json={"customer_id": 1})
    assert response.status_code == 400


def test_backend_chat_respects_budget(backend_client, monkeypatch):
    backend = sys.modules["student5_backend_api"]

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    monkeypatch.setattr(
        backend,
        "call_ollama",
        lambda prompt: "Try the Nike Air Force 1 Low and Puma Future Rider.",
    )
    monkeypatch.setattr(backend, "db_put", lambda path, payload: FakeResponse())
    monkeypatch.setattr(backend, "db_delete", lambda path: FakeResponse())
    monkeypatch.setattr(
        backend,
        "db_post",
        lambda path, payload: FakeResponse(201, {"recommendation_id": 1}),
    )
    monkeypatch.setattr(backend, "db_get", lambda path, **params: FakeResponse(200, []))
    monkeypatch.setattr(backend, "get_customer_context", lambda cid: ({}, [], set()))

    response = backend_client.post(
        "/api/chat",
        json={"customer_id": 1, "message": "shoes under 120"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommendations"]
    for item in payload["recommendations"]:
        assert item["product"]["price"] <= 120


def test_frontend_index_loads(frontend_client):
    response = frontend_client.get("/")
    assert response.status_code == 200
    assert b"Shoe shopping assistant" in response.data


def test_database_preferences_create(database_client):
    response = database_client.post(
        "/preferences",
        json={
            "customer_id": 42,
            "product_category_interests": "street",
            "preferred_brands": "Nike",
            "price_range_min": 50,
            "price_range_max": 200,
        },
    )
    assert response.status_code == 201

    get_response = database_client.get("/preferences/42")
    assert get_response.status_code == 200
    assert get_response.get_json()["preferred_brands"] == "Nike"
