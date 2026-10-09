"""Normal startup must preserve Orders; demo replacement is explicit."""
import importlib.util
from pathlib import Path
import sqlite3

import pytest


def initializer():
    spec = importlib.util.spec_from_file_location(
        "orders_init_test", Path(__file__).resolve().parents[1] / "database/init_db.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(path):
    with sqlite3.connect(path) as db:
        return (db.execute("SELECT * FROM orders").fetchall(),
                db.execute("SELECT * FROM order_items").fetchall())


def test_initialization_creates_empty_schema_and_parent_directory(tmp_path):
    path = tmp_path / "data" / "orders.db"
    initializer().initialize(path)
    assert snapshot(path) == ([], [])


def test_repeated_startup_preserves_orders_items_status_and_next_id(tmp_path):
    path = tmp_path / "orders.db"
    init = initializer()
    init.seed(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE orders SET status = 'CANCELLED' WHERE order_id = 1")
        db.execute("INSERT INTO orders(customer_id,total_amount) VALUES(99,12)")
        order_id = db.execute("SELECT max(order_id) FROM orders").fetchone()[0]
        db.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price,subtotal) VALUES(?,99,1,12,12)", (order_id,))
    before = snapshot(path)
    init.initialize(path)
    init.initialize(path)
    assert snapshot(path) == before
    with sqlite3.connect(path) as db:
        cursor = db.execute("INSERT INTO orders(customer_id,total_amount) VALUES(99,1)")
        assert cursor.lastrowid > order_id


def test_demo_seed_refuses_to_replace_existing_data(tmp_path):
    path = tmp_path / "orders.db"
    init = initializer()
    init.seed(path)
    before = snapshot(path)
    with pytest.raises(ValueError, match="already contains orders"):
        init.seed(path)
    assert snapshot(path) == before


def test_explicit_demo_reset_replaces_data_and_keeps_item_relationships(tmp_path):
    path = tmp_path / "orders.db"
    init = initializer()
    init.seed(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE orders SET customer_id = 99")
    init.seed(path, reset=True)
    orders, items = snapshot(path)
    assert len(orders) == len(items) == 10
    assert all(row[1] in (1, 2, 3) for row in orders)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_seed_handles_empty_database_with_existing_sequence(tmp_path):
    path = tmp_path / "orders.db"
    init = initializer()
    init.seed(path)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM order_items")
        db.execute("DELETE FROM orders")
    init.seed(path)
    orders, items = snapshot(path)
    assert {row[0] for row in orders} == {row[1] for row in items}
    assert min(row[0] for row in orders) > 10
