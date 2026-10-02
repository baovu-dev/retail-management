"""Offline contract/security tests. HTTP/MCP dependencies are mocked here."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
from itsdangerous import URLSafeTimedSerializer

from test_backend import load_backend

ROOT = Path(__file__).resolve().parents[2]
SECRET = "orders-test-secret-with-at-least-32-characters"
SESSION_SECRET = "session-test-secret-with-at-least-32-characters"
ORIGIN = "http://localhost:3004"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def token(order_id=1, customer_id=7, secret=SECRET, **overrides):
    claims = dict(aud="orders-mcp", scope="order:status", order_id=order_id,
                  role="customer", customer_id=customer_id)
    claims.update(overrides)
    return URLSafeTimedSerializer(secret, salt="orders-mcp-status-v1").dumps(claims)


def auth(value):
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setenv("ORDERS_MCP_SECRET", SECRET)
    monkeypatch.setenv("MCP_ENABLED", "true")
    return load_backend()


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SESSION_SECRET)
    monkeypatch.setenv("ORDERS_MCP_SECRET", SECRET)
    monkeypatch.setenv("ORDERS_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("STAFF_PASSWORD", "private-test-staff-password")
    return load_file("shared_mcp_test", "shared/backend/app.py")


@pytest.mark.parametrize("login_body", [{"customer": {"customer_id": 7}}, {"message": "Login successful", "customer_id": 7}])
def test_shared_login_issues_order_scoped_token(shared, login_body):
    customer_response = Mock(status_code=200)
    customer_response.json.return_value = login_body
    with shared.app.test_client() as client, patch.object(shared.requests, "post", return_value=customer_response):
        assert client.post("/login", data={"email": "test@example.com", "password": "test"}).status_code == 302
        response = client.post("/api/orders/mcp-token", headers={"Origin": ORIGIN},
                               json={"order_id": 1, "customer_id": 999, "role": "staff"})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Cache-Control"] == "no-store"
    claims = URLSafeTimedSerializer(SECRET, salt="orders-mcp-status-v1").loads(response.json["access_token"], max_age=120)
    assert claims == dict(aud="orders-mcp", scope="order:status", order_id=1, role="customer", customer_id=7)


def test_shared_rejects_no_session_forged_session_and_untrusted_origin(shared):
    with shared.app.test_client() as client:
        url = "/api/orders/mcp-token"
        assert client.post(url, headers={"Origin": ORIGIN, "X-Customer-ID": "7"}, json={"order_id": 1}).status_code == 401
        serializer = shared.app.session_interface.get_signing_serializer(shared.app)
        old_key = shared.app.secret_key
        shared.app.secret_key = "kicklab-dev-secret-key"
        forged = shared.app.session_interface.get_signing_serializer(shared.app).dumps({"customer": {"customer_id": 7}})
        shared.app.secret_key = old_key
        client.set_cookie("session", forged)
        assert client.post(url, headers={"Origin": ORIGIN}, json={"order_id": 1}).status_code == 401
        client.set_cookie("session", serializer.dumps({"customer": {"customer_id": 7}}))
        for origin in ("http://evil.example", "null", ""):
            assert client.post(url, headers={"Origin": origin}, json={"order_id": 1}).status_code == 403
        preflight = client.options(url, headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "content-type"})
        assert preflight.headers["Access-Control-Allow-Credentials"] == "true"
        assert preflight.headers["Access-Control-Allow-Origin"] == ORIGIN


def test_shared_fails_closed_with_default_keys(shared, monkeypatch):
    with shared.app.test_client() as client:
        shared.app.secret_key = "kicklab-dev-secret-key"
        assert client.post("/api/orders/mcp-token", headers={"Origin": ORIGIN}, json={"order_id": 1}).status_code == 503
        shared.app.secret_key = SESSION_SECRET
        monkeypatch.delenv("ORDERS_MCP_SECRET")
        assert client.post("/api/orders/mcp-token", headers={"Origin": ORIGIN}, json={"order_id": 1}).status_code == 503


def test_shared_staff_token_and_logout(shared):
    with shared.app.test_client() as client:
        assert client.post("/staff-login", data={"email": shared.STAFF_EMAIL, "password": shared.STAFF_PASSWORD}).status_code == 302
        response = client.post("/api/orders/mcp-token", headers={"Origin": ORIGIN}, json={"order_id": 1})
        claims = URLSafeTimedSerializer(SECRET, salt="orders-mcp-status-v1").loads(response.json["access_token"])
        assert claims["role"] == "staff"
        client.get("/staff-logout")
        assert client.post("/api/orders/mcp-token", headers={"Origin": ORIGIN}, json={"order_id": 1}).status_code == 401


def test_shared_default_staff_password_cannot_issue_token(shared, monkeypatch):
    monkeypatch.setattr(shared, "STAFF_PASSWORD", "Admin1234")
    with shared.app.test_client() as client:
        with client.session_transaction() as session:
            session["is_staff"] = True
            session["staff_email"] = shared.STAFF_EMAIL
        assert client.post("/api/orders/mcp-token", headers={"Origin": ORIGIN}, json={"order_id": 1}).status_code == 503


@pytest.mark.parametrize("order_id", [None, 0, -1, True, 1.5, "1", "1 OR 1=1", 2147483648])
def test_bad_id_never_calls_mcp(backend, order_id):
    with patch.object(backend, "call_order_status") as call:
        response = backend.app.test_client().post("/api/mcp/order-status", json={"order_id": order_id}, headers=auth(token()))
    assert response.status_code == 400
    call.assert_not_called()


def test_backend_executes_registered_tool_contract(backend):
    credential = token()
    with patch.object(backend, "call_order_status", return_value={"order_id": 1, "status": "CONFIRMED"}) as call:
        response = backend.app.test_client().post("/api/mcp/order-status", json={"order_id": 1}, headers=auth(credential))
    call.assert_called_once_with(1, credential)
    assert response.json == {"order_id": 1, "status": "CONFIRMED", "source": "mcp", "tool": "get_order_status"}


@pytest.mark.parametrize("credential,status", [
    ("", 401), ("forged", 401), (token(secret="wrong-signing-key"), 401),
    (token(order_id=2), 403), (token(aud="other"), 401), (token(scope="order:write"), 401),
    (token(role="admin"), 401), (token(customer_id=True), 401),
])
def test_auth_rejected_at_both_entry_points(backend, credential, status):
    with patch.object(backend, "call_order_status") as call, patch.object(backend, "db_get") as db:
        client = backend.app.test_client()
        headers = {**auth(credential), "X-Customer-ID": "7", "X-Role": "staff"}
        assert client.post("/api/mcp/order-status", json={"order_id": 1, "customer_id": 7}, headers=headers).status_code == status
        assert client.get("/api/internal/mcp/orders/1/status", headers=headers).status_code == status
    call.assert_not_called()
    db.assert_not_called()


def test_expired_token_is_rejected(backend):
    with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1):
        expired = token()
    client = backend.app.test_client()
    assert client.post("/api/mcp/order-status", json={"order_id": 1}, headers=auth(expired)).status_code == 401
    assert client.get("/api/internal/mcp/orders/1/status", headers=auth(expired)).status_code == 401


@pytest.mark.parametrize("owner,credential,expected", [
    (7, token(), 200), (8, token(), 403),
    (8, token(role="staff", staff_email="staff@example.com"), 200),
])
def test_internal_checks_owner_and_returns_minimum_fields(backend, owner, credential, expected):
    record = Mock(status_code=200)
    record.json.return_value = {"order_id": 1, "customer_id": owner, "status": "PENDING", "items": ["private"]}
    with patch.object(backend, "db_get", return_value=record), patch.object(backend, "call_order_status") as call:
        response = backend.app.test_client().get("/api/internal/mcp/orders/1/status", headers=auth(credential))
    assert response.status_code == expected
    assert "customer_id" not in response.json and "items" not in response.json
    call.assert_not_called()  # Internal route must never recurse into MCP.


@pytest.mark.parametrize("database_status,expected", [(404, 404), (500, 503), (503, 503)])
def test_internal_missing_order_or_database_failure(backend, database_status, expected):
    with patch.object(backend, "db_get", return_value=Mock(status_code=database_status)):
        response = backend.app.test_client().get("/api/internal/mcp/orders/1/status", headers=auth(token()))
    assert response.status_code == expected


def test_mcp_unavailable_and_disabled(backend, monkeypatch):
    client = backend.app.test_client()
    with patch.object(backend, "call_order_status", side_effect=RuntimeError("credential-must-not-leak")) as call:
        response = client.post("/api/mcp/order-status", json={"order_id": 1}, headers=auth(token()))
        assert response.status_code == 503
        assert "credential-must-not-leak" not in response.text
        call.reset_mock()
        monkeypatch.setenv("MCP_ENABLED", "false")
        assert client.post("/api/mcp/order-status", json={"order_id": 1}, headers=auth(token())).status_code == 403
        assert client.get("/api/internal/mcp/orders/1/status", headers=auth(token())).status_code == 403
        call.assert_not_called()


def test_missing_config_and_oversized_token_fail_closed(backend, monkeypatch):
    client = backend.app.test_client()
    with patch.object(backend, "call_order_status") as call:
        assert client.post("/api/mcp/order-status", json={"order_id": 1}, headers=auth("x" * 4097)).status_code == 401
        monkeypatch.delenv("ORDERS_MCP_SECRET")
        assert client.post("/api/mcp/order-status", json={"order_id": 1}, headers=auth(token())).status_code == 503
        monkeypatch.delenv("MCP_ENABLED")
        assert client.post("/api/mcp/order-status", json={"order_id": 1}, headers=auth(token())).status_code == 403
        call.assert_not_called()


def test_orders_tool_uses_fixed_authenticated_read_endpoint(monkeypatch):
    tool = load_file("orders_tool_test", "ai-services/mcp-server/tools/student4_orders.py")
    monkeypatch.setenv("ORDERS_API_URL", "http://orders.test:5004")
    response = Mock(status_code=200)
    response.json.return_value = {"order_id": 1, "status": "PENDING", "customer_id": 7}
    with patch.object(tool.requests, "get", return_value=response) as get:
        assert tool.get_order_status(1, "credential") == {"order_id": 1, "status": "PENDING"}
        get.assert_called_once_with("http://orders.test:5004/api/internal/mcp/orders/1/status",
                                    headers=auth("credential"), timeout=5, allow_redirects=False)
    with patch.object(tool.requests, "get", side_effect=requests.Timeout("secret")):
        assert tool.get_order_status(1, "credential")["code"] == "unavailable"


def test_frontend_links_use_shared_origin(monkeypatch):
    monkeypatch.setenv("SHARED_BASE", "http://localhost:5500")
    frontend = load_file("orders_frontend_test", "student-4/frontend/app.py")
    client = frontend.app.test_client()
    assert 'href="http://localhost:5500/staff_dashboard"' in client.get("/admin").text
    html = client.get("/").text
    assert 'const SHARED_BASE = "http://localhost:5500"' in html
    assert 'credentials: "include"' in html
    assert '/api/mcp/order-status' in html


@pytest.mark.parametrize("status", ["PENDING", "CONFIRMED", "CANCELLED"])
def test_orders_tool_normal_response(status):
    tool = load_file("orders_tool_normal", "ai-services/mcp-server/tools/student4_orders.py")
    response = Mock(status_code=200)
    response.json.return_value = {"order_id": 1, "status": status, "customer_id": 7}
    with patch.object(tool.requests, "get", return_value=response):
        assert tool.get_order_status(1, "test-token") == {"order_id": 1, "status": status}


@pytest.mark.parametrize("body", [
    None, [], "PENDING", 42, {},
    {"order_id": True, "status": "PENDING"}, {"order_id": "1", "status": "PENDING"},
    {"order_id": 2, "status": "PENDING"}, {"order_id": 1, "status": []},
    {"order_id": 1, "status": {}}, {"order_id": 1, "status": None},
    {"order_id": 1, "status": True}, {"order_id": 1, "status": "SHIPPED"},
])
def test_orders_tool_rejects_invalid_response_types(body):
    tool = load_file("orders_tool_invalid", "ai-services/mcp-server/tools/student4_orders.py")
    response = Mock(status_code=200)
    response.json.return_value = body
    with patch.object(tool.requests, "get", return_value=response):
        assert tool.get_order_status(1, "test-token")["code"] == "unavailable"


@pytest.mark.parametrize("order_id", [True, "1", 1.5, 0, -1, 2147483648])
def test_orders_tool_rejects_invalid_id_before_http(order_id):
    tool = load_file("orders_tool_id", "ai-services/mcp-server/tools/student4_orders.py")
    with patch.object(tool.requests, "get") as get:
        assert tool.get_order_status(order_id, "test-token")["code"] == "invalid_input"
        get.assert_not_called()
