"""Exercise actual shared sessions, signed capabilities, Flask routes and SQLite."""
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import pytest
from itsdangerous import URLSafeTimedSerializer

from test_backend import load_backend
from test_orders_mcp import load_file

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = "fixture.australiaeast.azurecontainerapps.io"
ORIGIN = f"https://student4-frontend.{DOMAIN}"
TOKEN_HEADERS = {"Origin": ORIGIN, "X-Orders-Token-Request": "1"}


class Reply:
    def __init__(self, response):
        self.response, self.status_code, self.headers = response, response.status_code, response.headers
        self.ok, self.is_redirect = self.status_code < 400, 300 <= self.status_code < 400

    def json(self):
        return self.response.get_json()

    def iter_content(self, size):
        yield self.response.data

    def close(self):
        pass


@pytest.fixture
def system(monkeypatch, tmp_path):
    secret, staff_password, customer_password = (secrets.token_hex(32) for _ in range(3))
    for key, value in {"ORDERS_CRUD_SECRET": secret, "SECRET_KEY": secrets.token_hex(32),
                       "ORDERS_MCP_SECRET": secrets.token_hex(32), "ORDERS_PURCHASE_SECRET": secrets.token_hex(32),
                       "ORDERS_FRONTEND_ORIGIN": ORIGIN,
                       "APP_ENV": "local", "STAFF_EMAIL": "staff@example.test", "STAFF_PASSWORD": staff_password,
                       "AI_ENABLED": "false", "MCP_ENABLED": "false", "RAG_ENABLED": "false", "MULTI_AGENT_ENABLED": "false"}.items():
        monkeypatch.setenv(key, value)
    database = load_file("crud_database_fixture", "student-4/database/app.py")
    database.DB_PATH = str(tmp_path / "orders.sqlite")
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.executescript((ROOT / "student-4/database/schema.sql").read_text())
    backend = load_backend()
    shared = load_file("crud_shared_fixture", "shared/backend/app.py")
    frontend = load_file("crud_frontend_fixture", "student-4/frontend/app.py")
    frontend.API_BASE, frontend.SHARED_BASE = f"https://student4-backend.{DOMAIN}", f"https://shared-backend.{DOMAIN}"
    db_calls = []
    def database_call(method, path, payload=None):
        db_calls.append((method, path, payload))
        return Reply(database.app.test_client().open(path, method=method, json=payload))
    for name, method in (("db_get", "GET"), ("db_post", "POST"), ("db_put", "PUT"), ("db_delete", "DELETE")):
        monkeypatch.setattr(backend, name, lambda path, payload=None, method=method: database_call(method, path, payload))
    product = {"product_id": 101, "price": 0.01, "name": "Synthetic shoe", "category": "Test", "brand": "Test"}
    def get(url, **kwargs):
        if url.startswith(shared.PRODUCTS_API):
            result = Mock(ok=True, status_code=200)
            result.json.return_value = product
            return result
        if url.startswith(shared.ORDERS_API):
            return Reply(backend.app.test_client().get(urlsplit(url).path, headers=kwargs.get("headers", {})))
        raise AssertionError("Unexpected upstream GET")
    def post(url, **kwargs):
        if url == shared.CUSTOMERS_API + "/login":
            data = kwargs["json"]
            ids = {"owner@example.test": 1, "other@example.test": 2}
            result = Mock(status_code=200 if data.get("email") in ids and data.get("password") == customer_password else 401)
            result.json.return_value = {"customer_id": ids.get(data.get("email")), "first_name": "Test"}
            return result
        if url == shared.ORDERS_API + "/api/orders":
            return Reply(backend.app.test_client().post("/api/orders", json=kwargs["json"], headers=kwargs.get("headers", {})))
        raise AssertionError("Unexpected upstream POST")
    monkeypatch.setattr(shared.requests, "get", get)
    monkeypatch.setattr(shared.requests, "post", post)
    accounts = {"owner": {"email": "owner@example.test", "password": customer_password, "customer_id": 1},
                "other": {"email": "other@example.test", "password": customer_password, "customer_id": 2},
                "staff": {"email": "staff@example.test", "password": staff_password}}
    clients = {role: shared.app.test_client() for role in accounts}
    for role, account in accounts.items():
        assert clients[role].post("/login", data={key: account[key] for key in ("email", "password")}).status_code == 302
    def issue(role):
        reply = clients[role].post("/api/orders/crud-token", headers=TOKEN_HEADERS,
                                   json={"customer_id": 999, "staff_email": "forged@example.test", "role": "staff"})
        assert reply.status_code == 200
        return {"Authorization": "Bearer " + reply.json["access_token"]}
    return SimpleNamespace(backend=backend, shared=shared, frontend=frontend, database=database,
                           clients=clients, issue=issue, accounts=accounts, secret=secret, db_calls=db_calls,
                           api=backend.app.test_client(), item={"product_id": 101, "quantity": 1, "unit_price": 0.01})


def create(system, role="owner"):
    response = system.api.post("/api/orders", headers=system.issue(role), json={"items": [system.item]})
    assert response.status_code == 201
    return response.json["order_id"]


@pytest.mark.parametrize("method,path", [("GET", "/api/orders"), ("GET", "/api/orders/1"),
                                         ("POST", "/api/orders"), ("PUT", "/api/orders/1"), ("DELETE", "/api/orders/1")])
def test_anonymous_requests_denied_before_database_or_input_validation(system, method, path):
    response = system.api.open(path, method=method, json={})
    assert response.status_code == 401 and response.json["code"] == "unauthorized"
    assert not system.db_calls


@pytest.mark.parametrize("kind", ["forged", "expired", "mcp", "review", "wrong_scope", "wrong_audience", "wrong_role"])
def test_invalid_or_other_capability_domains_are_rejected(system, kind):
    claims = {"aud": "orders-crud", "iss": "kicklab-shared", "scope": "orders:customer:crud", "role": "customer", "customer_id": 1}
    signer = URLSafeTimedSerializer(system.secret, salt="orders-crud-v1")
    if kind == "forged":
        token = "forged"
    elif kind == "expired":
        earlier = time.time() - 121
        with patch("itsdangerous.timed.time.time", return_value=earlier):
            token = signer.dumps(claims)
    elif kind in {"mcp", "review"}:
        token = URLSafeTimedSerializer(os.environ["ORDERS_MCP_SECRET"], salt="orders-mcp-status-v1" if kind == "mcp" else "orders-multi-agent-v1").dumps(claims)
    else:
        claims[{"wrong_scope": "scope", "wrong_audience": "aud", "wrong_role": "role"}[kind]] = "wrong"
        token = signer.dumps(claims)
    response = system.api.get("/api/orders", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert not system.db_calls


def test_customer_identity_is_session_bound_and_database_isolation_is_enforced(system):
    first, second = create(system), create(system, "other")
    own = system.api.get("/api/orders", headers=system.issue("owner"))
    assert [row["order_id"] for row in own.json] == [first]
    for method in ("GET", "DELETE"):
        denied = system.api.open(f"/api/orders/{second}", method=method, headers=system.issue("owner"))
        assert denied.status_code == 403 and denied.json["code"] == "forbidden"
    assert system.api.get("/api/orders?customer_id=2", headers=system.issue("owner")).status_code == 403
    assert system.api.post("/api/orders", headers=system.issue("owner"), json={"customer_id": 2, "items": [system.item]}).status_code == 403
    assert system.api.put(f"/api/orders/{first}", headers=system.issue("owner"), json={"status": "CONFIRMED", "staff_email": "forged@example.test"}).status_code == 403
    assert len(system.api.get("/api/orders", headers=system.issue("staff")).json) == 2


def test_staff_confirm_customer_cancel_and_retention_preserve_existing_behaviour(system):
    order = create(system)
    assert system.api.post("/api/orders", headers=system.issue("staff"), json={"items": [system.item], "customer_id": 1}).status_code == 403
    assert system.api.put(f"/api/orders/{order}", headers=system.issue("staff"), json={"status": "CONFIRMED"}).status_code == 200
    assert system.api.delete(f"/api/orders/{order}", headers=system.issue("owner")).status_code == 200
    persisted = system.api.get(f"/api/orders/{order}", headers=system.issue("owner"))
    assert persisted.json["status"] == "CANCELLED" and len(persisted.json["items"]) == 1
    assert system.api.put(f"/api/orders/{order}", headers=system.issue("staff"), json={"status": "CONFIRMED"}).status_code == 409
    assert system.api.delete(f"/api/orders/{order}", headers=system.issue("staff")).status_code == 200


def test_order_ai_cannot_disclose_another_customer_and_disabled_profile_stays_disabled(system, monkeypatch):
    order = create(system, "other")
    monkeypatch.setenv("AI_ENABLED", "true")
    with patch.object(system.backend, "ask_ollama", return_value="Supported answer.") as model:
        assert system.api.post("/api/order-assistant", json={"order_id": order, "question": "Status?"}).status_code == 401
        assert system.api.post("/api/order-assistant", headers=system.issue("owner"), json={"order_id": order, "question": "Status?"}).status_code == 403
        model.assert_not_called()
        assert system.api.post("/api/order-assistant", headers=system.issue("other"), json={"order_id": order, "question": "Status?"}).status_code == 200
    monkeypatch.setenv("AI_ENABLED", "false")
    assert system.api.post("/api/order-assistant", json={}).json["code"] == "disabled"


def test_token_issuance_cors_csrf_identity_and_logout(system):
    client = system.clients["owner"]
    result = client.post("/api/orders/crud-token", headers=TOKEN_HEADERS, json={"customer_id": 2, "staff_email": "forged"})
    assert result.json["customer_id"] == 1 and result.json["role"] == "customer"
    assert result.json["expires_in"] == 120
    assert result.headers["Cache-Control"] == "no-store"
    assert result.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert result.headers["Access-Control-Allow-Credentials"] == "true"
    evil = client.post("/api/orders/crud-token", headers={"Origin": "https://evil.example", "X-Orders-Token-Request": "1"})
    assert evil.status_code == 403 and "Access-Control-Allow-Origin" not in evil.headers
    assert client.post("/api/orders/crud-token", headers={"Origin": ORIGIN}).status_code == 403
    client.get("/logout")
    assert client.post("/api/orders/crud-token", headers=TOKEN_HEADERS).status_code == 401
    preflight = system.api.options("/api/orders", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"})
    assert preflight.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "Access-Control-Allow-Credentials" not in preflight.headers


@pytest.mark.parametrize("problem", ["missing_secret", "weak_secret", "missing_cloud_origin", "insecure_cloud_origin"])
def test_configuration_errors_never_enable_public_crud(system, monkeypatch, problem):
    headers = system.issue("owner")
    if problem == "missing_secret":
        monkeypatch.delenv("ORDERS_CRUD_SECRET")
    elif problem == "weak_secret":
        monkeypatch.setenv("ORDERS_CRUD_SECRET", "weak")
    else:
        monkeypatch.setenv("APP_ENV", "cloud")
        if problem == "missing_cloud_origin":
            monkeypatch.delenv("ORDERS_FRONTEND_ORIGIN")
        else:
            monkeypatch.setenv("ORDERS_FRONTEND_ORIGIN", "http://localhost:3004")
    assert system.api.get("/api/orders", headers=headers).status_code == 503
    # Shared origin is fixed at startup; re-import represents the same new configuration.
    shared = load_file("crud_misconfigured_shared", "shared/backend/app.py")
    with shared.app.test_client() as client:
        with client.session_transaction() as session:
            session["customer"] = {"customer_id": 1}
        origin = shared.ORDERS_FRONTEND_ORIGIN
        assert client.post("/api/orders/crud-token", headers={"Origin": origin, "X-Orders-Token-Request": "1"}).status_code == 503
    assert not system.db_calls


def test_checkout_uses_server_session_credentials_and_blocks_cross_customer_success(system):
    owner = system.clients["owner"]
    form = owner.get("/order/101")
    assert form.status_code == 200 and b'name="orders_csrf"' in form.data
    with owner.session_transaction() as session:
        csrf = session["orders_checkout_csrf"]
    response = owner.post("/order/101/place", data={"quantity": "1", "orders_csrf": csrf, "customer_id": 2}, headers={"Origin": "http://localhost"})
    assert response.status_code == 302
    assert owner.get(response.location).status_code == 200
    order_id = int(response.location.rsplit("/", 1)[1])
    assert system.api.get(f"/api/orders/{order_id}", headers=system.issue("owner")).json["customer_id"] == 1
    assert system.clients["other"].get(response.location).status_code == 403
    before = len(system.db_calls)
    assert owner.post("/order/101/place", data={"orders_csrf": csrf}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert owner.post("/order/101/place", data={}, headers={"Origin": "http://localhost"}).status_code == 403
    assert len(system.db_calls) == before


def test_customer_and_staff_templates_render_authenticated_requests(system):
    client = system.frontend.app.test_client()
    for path, role in (("/", "customer"), ("/admin", "staff")):
        html = client.get(path).get_data(as_text=True)
        assert 'const expectedRole = "' + role + '"' in html
        assert "X-Orders-Token-Request" in html
        assert "Bearer ${capability.access_token}" in html
        assert "await ordersFetch(" in html
        assert "await fetch(ordersUrl)" not in html
        assert "?customer_id=${" not in html


def test_cloud_cookie_flags_and_secret_ingress_configuration(system, monkeypatch):
    monkeypatch.setenv("APP_ENV", "cloud")
    shared = load_file("crud_cloud_cookies", "shared/backend/app.py")
    response = shared.app.test_client().post("/staff-login", data=system.accounts["staff"], base_url=f"https://shared-backend.{DOMAIN}")
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=None" in cookie
    config = {"ENV_DOMAIN": DOMAIN, "LOGIN_SERVER": "fixture.azurecr.io", "IMAGE_TAG": "a" * 40,
              "ENV_ID": "/fixture/environment", "PULL_ID": "/fixture/identity", "LOCATION": "australiaeast",
              "SECRET_KEY": secrets.token_hex(32), "ORDERS_MCP_SECRET": secrets.token_hex(32), "ORDERS_CRUD_SECRET": system.secret,
              "STAFF_PASSWORD": system.accounts["staff"]["password"],
              "CUSTOMERS_REVIEW_SECRET": secrets.token_hex(32)}
    for key, value in config.items():
        monkeypatch.setenv(key, value)
    for app in ("student4-database", "student4-backend", "shared-backend", "student1-backend"):
        output = io.StringIO()
        with patch.object(sys, "argv", ["render", str(ROOT / "scripts/deploy/apps.conf"), app]), redirect_stdout(output):
            load_file("crud_cloud_spec_" + app, "scripts/deploy/render_app_spec.py")
        spec = json.loads(output.getvalue())
        if app == "student4-database":
            assert spec["properties"]["configuration"]["ingress"]["external"] is False
            assert not spec["properties"]["configuration"]["secrets"]
        else:
            env = spec["properties"]["template"]["containers"][0]["env"]
            assert {"name": "ORDERS_PURCHASE_SECRET", "secretRef": "orders-purchase-secret"} in env  # pragma: allowlist secret - reference name only
            if app == "student1-backend":
                assert {entry["name"] for entry in env if "secretRef" in entry} == {"ORDERS_PURCHASE_SECRET"}
                assert {"name": "ORDERS_API_URL", "value": f"https://student4-backend.{DOMAIN}"} in env
                continue
            if app == "shared-backend":
                assert {"name": "REVIEWS_FRONTEND_ORIGIN", "value": f"https://student1-backend.{DOMAIN}"} in env
                assert {"name": "CUSTOMERS_REVIEW_SECRET", "secretRef": "customers-review-secret"} in env  # pragma: allowlist secret - reference name only
            assert {"name": "ORDERS_CRUD_SECRET", "secretRef": "orders-crud-secret"} in env  # pragma: allowlist secret - secret reference name only
            assert {"name": "APP_ENV", "value": "cloud"} in env


def test_real_session_issuer_to_collector_to_api_sqlite_flow(system, monkeypatch, tmp_path):
    module = load_file("crud_cloud_collector_integration", "scripts/orders/cloud_evidence.py")
    monkeypatch.setattr(module, "public_dns", lambda origins: None)
    config = {"environment_domain": DOMAIN, "commit_sha": "a" * 40, "run_id": 39419555443,
              "frontend_origin": ORIGIN, "api_origin": f"https://student4-backend.{DOMAIN}", "shared_origin": f"https://shared-backend.{DOMAIN}",
              "images": {key: "fixture.azurecr.io/student-4:aaaaaaa" for key in ("student4-backend", "student4-frontend")}}
    class LoginSession:
        def __init__(self):
            self.client = system.shared.app.test_client()
        def post(self, url, **kwargs):
            return Reply(self.client.post(urlsplit(url).path, data=kwargs.get("data"), headers=kwargs.get("headers")))
        def close(self):
            pass
    provider = module.SessionCredentials(config, system.accounts, session_factory=LoginSession)
    session = Mock()
    def request(method, url, **kwargs):
        target = system.frontend.app if url.startswith(ORIGIN) else system.backend.app
        return Reply(target.test_client().open(urlsplit(url).path, method=method, headers=kwargs["headers"], json=kwargs["json"]))
    session.request.side_effect = request
    run = module.Collector(config, system.accounts, 101, 0.01, tmp_path / "mock-only.json", session=session,
                           browser_probe=lambda *args: {"http_status": 200, "cors_allowed": True, "count": 0},
                           resolve=lambda *args: None, token_provider=provider, delay=0)
    assert run.run()
    provider.close()
    assert run.report["checks"]["ownership_denied"]["passed"]
    assert run.report["checks"]["read_after_cancel"]["observed"]["items_preserved"]
    raw = run.output.read_text()
    assert system.secret not in raw and system.accounts["owner"]["password"] not in raw
