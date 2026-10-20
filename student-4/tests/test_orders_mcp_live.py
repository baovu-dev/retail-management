import asyncio
from contextlib import contextmanager
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from flask import Flask, jsonify
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import pytest
import requests
from werkzeug.serving import make_server

from test_orders_mcp import ROOT, ORIGIN, auth, load_file, token

pytestmark = pytest.mark.skipif(os.getenv("RUN_ORDERS_MCP_LIVE") != "1", reason="Opt-in: starts isolated loopback services")


@contextmanager
def serving(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def extract(result):
    assert not result.isError
    return result.structuredContent or json.loads(result.content[0].text)


# Reuse fixtures without loading applications or contacting services at collection time.
from test_orders_mcp import backend, shared  # noqa: E402,F401


def test_real_mcp_transport_ownership_and_reviews_regression(backend, shared, monkeypatch, tmp_path):
    database = load_file("orders_live_database", "student-4/database/app.py")
    database.DB_PATH = str(tmp_path / "isolated-orders.db")
    # Schema (including DROP) is applied ONLY to this newly created temporary file.
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.executescript((ROOT / "student-4/database/schema.sql").read_text())
    for customer in (7, 8):
        assert database.app.test_client().post("/orders", json={"customer_id": customer,
            "items": [{"product_id": 101, "quantity": 1, "unit_price": 10}]}).status_code == 201

    reviews = Flask("isolated_reviews_fixture")
    @reviews.get("/reviews/<int:product_id>")
    def review_rows(product_id):
        return jsonify([{"review_id": 1, "product_id": product_id, "rating": 4, "is_flagged": 1}])
    @reviews.get("/reviews")
    def all_reviews():
        return review_rows(101)

    # Actual shared token issuer and signed session; customer login service isn't under test here.
    with shared.app.test_client() as login:
        with login.session_transaction() as session:
            session["customer"] = {"customer_id": 7}
        credentials = {}
        for order_id in (1, 2, 999):
            response = login.post("/api/orders/mcp-token", headers={"Origin": ORIGIN}, json={"order_id": order_id})
            assert response.status_code == 200
            credentials[order_id] = response.json["access_token"]

    with serving(database.app) as db_url, serving(backend.app) as backend_url, serving(reviews) as reviews_url:
        monkeypatch.setattr(backend, "DATABASE_URL", db_url)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            mcp_port = reservation.getsockname()[1]
        mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"
        monkeypatch.setenv("MCP_URL", mcp_url)
        env = {**os.environ, "MCP_HOST": "127.0.0.1", "MCP_PORT": str(mcp_port),
               "ORDERS_API_URL": backend_url, "REVIEWS_DB_API": reviews_url}
        with (tmp_path / "mcp-server.log").open("w") as log:
            process = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT / "ai-services/mcp-server",
                                       env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    assert process.poll() is None, "MCP process exited; inspect temporary mcp-server.log"
                    try:
                        requests.get(mcp_url, timeout=0.2)
                        break
                    except requests.ConnectionError:
                        time.sleep(0.1)
                else:
                    pytest.fail("Isolated MCP server did not become ready")

                def public(order_id, credential):
                    return requests.post(f"{backend_url}/api/mcp/order-status", json={"order_id": order_id},
                                         headers=auth(credential), timeout=20)

                response = public(1, credentials[1])
                assert response.status_code == 200
                assert response.json() == {"order_id": 1, "status": "PENDING", "source": "mcp", "tool": "get_order_status"}
                assert public(2, credentials[2]).status_code == 403
                assert public(999, credentials[999]).status_code == 404
                assert public(0, credentials[1]).status_code == 400
                assert public(1, "forged").status_code == 401
                with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1):
                    expired = token()
                assert public(1, expired).status_code == 401

                async def direct_checks():
                    async with streamablehttp_client(mcp_url) as (read, write, _):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            names = {tool.name for tool in (await session.list_tools()).tools}
                            expected = {"get_order_status", "rating_summary", "reviews_by_product", "flagged_reviews",}
                            assert expected.issubset(names)
                            async def status(order_id, credential):
                                return extract(await session.call_tool("get_order_status", {"order_id": order_id, "access_token": credential}))
                            assert await status(1, credentials[1]) == {"order_id": 1, "status": "PENDING"}
                            assert (await status(2, credentials[2]))["code"] == "forbidden"
                            assert (await status(2, credentials[1]))["code"] == "forbidden"
                            assert (await status(1, "forged"))["code"] == "unauthorized"
                            assert (await status(1, expired))["code"] == "unauthorized"
                            assert (await status(999, credentials[999]))["code"] == "not_found"
                            assert (await status(0, credentials[1]))["code"] == "invalid_input"
                            summary = extract(await session.call_tool("rating_summary", {"product_id": 101}))
                            assert summary["average_rating"] == 4 and summary["review_count"] == 1
                            limited = extract(await session.call_tool("reviews_by_product", {"product_id": 101, "limit": 1}))
                            assert limited["count"] == 1
                            flagged = extract(await session.call_tool("flagged_reviews", {}))
                            assert flagged["count"] == 1
                            monkeypatch.setenv("MCP_ENABLED", "false")
                            assert (await status(1, credentials[1]))["code"] == "forbidden"
                asyncio.run(direct_checks())
                assert public(1, credentials[1]).status_code == 403
                monkeypatch.setenv("MCP_ENABLED", "true")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            # Real connection failure after stopping the test MCP process.
            assert public(1, credentials[1]).status_code == 503
