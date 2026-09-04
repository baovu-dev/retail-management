import importlib.util
import os
import sqlite3
import sys
import tempfile

import pytest

DATABASE_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "database"
)


def load_database_app():
    spec = importlib.util.spec_from_file_location(
        "student4_database",
        os.path.join(DATABASE_DIR, "app.py"),
    )

    module = importlib.util.module_from_spec(spec)

    sys.modules["student4_database"] = module

    spec.loader.exec_module(module)

    return module


@pytest.fixture
def database_client():
    temp_db = tempfile.NamedTemporaryFile(
        suffix=".db",
        delete=False
    )

    temp_db.close()

    db_app = load_database_app()

    db_app.DB_PATH = temp_db.name

    schema_path = os.path.join(
        DATABASE_DIR,
        "schema.sql"
    )

    with open(
        schema_path,
        encoding="utf-8"
    ) as schema_file:

        connection = sqlite3.connect(
            temp_db.name
        )

        connection.executescript(
            schema_file.read()
        )

        connection.commit()
        connection.close()

    db_app.app.config["TESTING"] = True

    with db_app.app.test_client() as client:
        yield client

    if os.path.exists(temp_db.name):
        os.unlink(temp_db.name)


def test_health(database_client):
    response = database_client.get(
        "/health"
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_create_order(database_client):
    response = database_client.post(
        "/orders",
        json={
            "customer_id": 1,
            "items": [
                {
                    "product_id": 101,
                    "quantity": 2,
                    "unit_price": 149.99
                }
            ]
        },
    )

    assert response.status_code == 201

    data = response.get_json()

    assert data["status"] == "PENDING"
    assert data["total_amount"] == 299.98
    assert "order_id" in data


def test_get_order(database_client):
    create = database_client.post(
        "/orders",
        json={
            "customer_id": 2,
            "items": [
                {
                    "product_id": 108,
                    "quantity": 1,
                    "unit_price": 99.99
                }
            ]
        },
    )

    order_id = create.get_json()["order_id"]

    response = database_client.get(
        f"/orders/{order_id}"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["customer_id"] == 2
    assert len(data["items"]) == 1

    assert (
        data["items"][0]["product_id"]
        == 108
    )


def test_update_order_status(database_client):
    create = database_client.post(
        "/orders",
        json={
            "customer_id": 3,
            "items": [
                {
                    "product_id": 103,
                    "quantity": 1,
                    "unit_price": 79.99
                }
            ]
        },
    )

    order_id = create.get_json()["order_id"]

    response = database_client.put(
        f"/orders/{order_id}",
        json={
            "status": "CONFIRMED"
        },
    )

    assert response.status_code == 200

    assert (
        response.get_json()["status"]
        == "CONFIRMED"
    )


def test_cancel_order(database_client):
    create = database_client.post(
        "/orders",
        json={
            "customer_id": 1,
            "items": [
                {
                    "product_id": 104,
                    "quantity": 1,
                    "unit_price": 110.00
                }
            ]
        },
    )

    order_id = create.get_json()["order_id"]

    response = database_client.delete(
        f"/orders/{order_id}"
    )

    assert response.status_code == 200

    assert (
        response.get_json()["status"]
        == "CANCELLED"
    )


def test_create_order_requires_items(
    database_client
):
    response = database_client.post(
        "/orders",
        json={
            "customer_id": 1,
            "items": []
        },
    )

    assert response.status_code == 400

    assert (
        response.get_json()["error"]
        == "At least one order item is required"
    )


def test_invalid_order_not_found(
    database_client
):
    response = database_client.get(
        "/orders/9999"
    )

    assert response.status_code == 404

    assert (
        response.get_json()["error"]
        == "Order not found"
    )


def test_invalid_order_status(
    database_client
):
    create = database_client.post(
        "/orders",
        json={
            "customer_id": 1,
            "items": [
                {
                    "product_id": 101,
                    "quantity": 1,
                    "unit_price": 149.99
                }
            ]
        },
    )

    order_id = create.get_json()["order_id"]

    response = database_client.put(
        f"/orders/{order_id}",
        json={
            "status": "DELIVERED"
        },
    )

    assert response.status_code == 400

    assert (
        response.get_json()["error"]
        == "status must be PENDING, CONFIRMED, or CANCELLED"
    )