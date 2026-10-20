"""Runs inside the built Orders image; never initializes a repository database."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

import requests


def serve_db():
    target = Path("/validation-data/orders.db")
    if not target.exists():
        # A brand-new file only: exclude DROP statements from the real schema.
        schema = Path("/app/database/schema.sql").read_text()
        statements = [s.strip() for s in schema.split(";") if s.strip()]
        create_only = [s for s in statements if s.startswith(("CREATE TABLE", "CREATE INDEX", "PRAGMA"))]
        assert len(create_only) == 6
        with sqlite3.connect(target) as connection:
            connection.executescript(";\n".join(create_only) + ";")
    spec = importlib.util.spec_from_file_location("image_database", "/app/database/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DB_PATH = str(target)
    module.app.run(host="0.0.0.0", port=6004, use_reloader=False)


def check():
    results = []

    def record(name, ok):
        results.append({"check": name, "result": "PASS" if ok else "FAIL"})
        if not ok:
            raise AssertionError(name)

    base = "http://backend:5004"
    try:
        for _ in range(60):
            try:
                if requests.get(base + "/api/health", timeout=1).json().get("database_connected"):
                    requests.get("http://frontend:3004/", timeout=1).raise_for_status()
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(.5)
        health = requests.get(base + "/api/health", timeout=5)
        record("built backend connects to built database", health.status_code == 200 and health.json()["database_connected"])
        created = requests.post(base + "/api/orders", json={"customer_id": 900001,
            "items": [{"product_id": 900002, "quantity": 2, "unit_price": 12.5}]}, timeout=5)
        record("new isolated order starts PENDING", created.status_code == 201 and created.json()["status"] == "PENDING")
        order_id = created.json()["order_id"]
        endpoint = base + f"/api/orders/{order_id}"
        before = requests.get(endpoint, timeout=5).json()
        record("order total and items", before["total_amount"] == 25 and len(before["items"]) == 1 and before["items"][0]["quantity"] == 2)
        confirmed = requests.put(endpoint, json={"status": "CONFIRMED"}, timeout=5)
        record("PENDING to CONFIRMED", confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED")
        invalid = requests.put(endpoint, json={"status": "SHIPPED"}, timeout=5)
        record("unimplemented shipping status rejected", invalid.status_code == 400)
        cancelled = requests.delete(endpoint, timeout=5)
        after = requests.get(endpoint, timeout=5)
        record("CONFIRMED can be cancelled", cancelled.status_code == 200 and after.json()["status"] == "CANCELLED")
        record("cancel preserves order and exact item records", after.status_code == 200 and after.json()["order_id"] == order_id
               and after.json()["items"] == before["items"] and after.json()["total_amount"] == before["total_amount"])
        record("missing order remains 404", requests.get(base + "/api/orders/2147483647", timeout=5).status_code == 404)
        for name, path, payload in [
            ("AI", "/api/order-assistant", {"order_id": order_id, "question": "Status?"}),
            ("MCP", "/api/mcp/order-status", {"order_id": order_id}),
            ("RAG", "/api/rag/answer", {"query": "Status?"})]:
            response = requests.post(base + path, json=payload, timeout=5)
            record(name + " disabled without contacting local AI services", response.status_code == 403 and response.json().get("code") == "disabled")
        html = requests.get("http://frontend:3004/", timeout=5).text
        record("built frontend contains MCP/RAG and browser API origin", all(s in html for s in ["mcpStatusForm", "ragForm", "http://localhost:5004"]))
        html = requests.get("http://frontend:3004/admin", timeout=5).text
        record("staff dashboard uses shared origin", "http://localhost:5000/staff_dashboard" in html)
    except Exception as exc:
        results.append({"check": "exception", "result": "FAIL", "detail": type(exc).__name__})
    print(json.dumps(results, indent=2), flush=True)
    return 1 if any(r["result"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    if sys.argv[1] == "serve-db":
        serve_db()
    else:
        raise SystemExit(check())
