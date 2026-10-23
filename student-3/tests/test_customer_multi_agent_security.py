"""Customer workflow privacy and staff decision boundaries."""

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from itsdangerous import URLSafeTimedSerializer


STUDENT = Path(__file__).resolve().parents[1]
REPO = STUDENT.parent
SECRET = "customers-review-private-test-key-32-characters"  # pragma: allowlist secret


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_exposes_only_aggregates():
    provider = load("customer_aggregate_test", REPO / "ai-services/multi-agent-server/evidence/student3_customers.py")
    response = Mock()
    response.json.return_value = [
        {"customer_id": 1, "first_name": "PrivateName", "email": "private@example.test", "phone": "1234", "status": "Active"},
        {"customer_id": 2, "first_name": "AnotherName", "email": "other@example.test", "status": "Inactive"},
    ]
    with patch.object(provider.requests, "get", return_value=response):
        result = provider.collect("Summarise customer 1 private@example.test")
    assert result["status"] == "success"
    assert len(result["records"]) == 3
    output = json.dumps(result)
    for private in ("PrivateName", "AnotherName", "private@example.test", "other@example.test", "1234", "customer 1"):
        assert private not in output
    assert "Total customer accounts: 2" in output


def test_provider_fails_closed_on_unknown_status():
    provider = load("customer_aggregate_invalid_test", REPO / "ai-services/multi-agent-server/evidence/student3_customers.py")
    response = Mock()
    response.json.return_value = [{"status": "Active", "email": "private@example.test"}, {"status": "unrecognized"}]
    with patch.object(provider.requests, "get", return_value=response):
        result = provider.collect("any")
    assert result["status"] == "error"
    assert "private@example.test" not in json.dumps(result)


def route_app(monkeypatch):
    monkeypatch.setenv("CUSTOMERS_REVIEW_SECRET", SECRET)
    monkeypatch.setenv("MULTI_AGENT_ENABLED", "true")
    routes = load("customer_multi_agent_test", STUDENT / "backend/routes/multi_agent_mode.py")
    app = Flask(__name__)
    app.register_blueprint(routes.multi_agent_bp)
    return app, routes


def staff_token():
    return URLSafeTimedSerializer(SECRET, salt="customers-review-v1").dumps({
        "iss": "kicklab-shared", "aud": "customers-review", "scope": "customers:review",
        "role": "staff", "staff_email": "staff@example.test"})


def test_start_requires_signed_staff_and_forces_aggregate_request(monkeypatch):
    app, routes = route_app(monkeypatch)
    client = app.test_client()
    assert client.post("/multi-agent/workflow").status_code == 401
    assert client.post("/multi-agent/workflow", headers={"Authorization": "Bearer fake"}).status_code == 401
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"feature": "student-3", "workflow_id": "ok"}
    with patch.object(routes.requests, "request", return_value=upstream) as call:
        response = client.post("/multi-agent/workflow", json={"user_request": "show alice@example.test"},
                               headers={"Authorization": f"Bearer {staff_token()}"})
    assert response.status_code == 200
    payload = call.call_args.kwargs["json"]
    assert payload["feature"] == "student-3"
    assert "alice@example.test" not in json.dumps(payload)


def test_decision_checks_feature_and_binds_staff_reviewer(monkeypatch):
    app, routes = route_app(monkeypatch)
    client = app.test_client()
    workflow_id = "a16a1cef-507b-4dc5-9181-1b5b5c343581"
    url = f"/multi-agent/workflow/{workflow_id}/decision"
    headers = {"Authorization": f"Bearer {staff_token()}"}
    with patch.object(routes.requests, "request") as call:
        call.return_value.status_code = 200
        call.return_value.json.return_value = {"feature": "student-4"}
        assert client.post(url, headers=headers, json={"decision": "Approve"}).status_code == 404
        assert call.call_count == 1
        call.return_value.json.side_effect = [{"feature": "student-3"}, {"status": "success"}]
        response = client.post(url, headers=headers, json={"decision": "Reject", "reviewer": "forged"})
    assert response.status_code == 200
    assert call.call_args.kwargs["json"]["reviewer"] == "staff@example.test"


def test_shared_mint_requires_staff_session_and_exact_origin(monkeypatch):
    monkeypatch.setenv("CUSTOMERS_REVIEW_SECRET", SECRET)
    monkeypatch.setenv("SECRET_KEY", "private-shared-cookie-key-32-characters")  # pragma: allowlist secret
    monkeypatch.setenv("STAFF_PASSWORD", "private-staff-password-32-characters")  # pragma: allowlist secret
    shared = load("shared_customer_review_test", REPO / "shared/backend/app.py")
    client = shared.app.test_client()
    headers = {"Origin": "http://localhost:5003", "X-Customers-Review-Request": "1"}
    assert client.post("/api/customers/review-token", headers=headers).status_code == 401
    with client.session_transaction() as session:
        session["is_staff"] = True
        session["staff_email"] = "admin@kicklab.com"
    assert client.post("/api/customers/review-token", headers={**headers, "Origin": "http://attacker.test"}).status_code == 403
    response = client.post("/api/customers/review-token", headers=headers)
    assert response.status_code == 200
    claims = URLSafeTimedSerializer(SECRET, salt="customers-review-v1").loads(response.json["access_token"])
    assert claims["staff_email"] == "admin@kicklab.com"
    assert response.headers["Cache-Control"] == "no-store"


def test_coordinator_blocks_unauthenticated_customer_history_and_decisions(monkeypatch):
    monkeypatch.setenv("CUSTOMERS_REVIEW_SECRET", SECRET)
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.syspath_prepend(str(REPO / "ai-services/multi-agent-server"))
    import app as coordinator_app

    workflow_id = "a16a1cef-507b-4dc5-9181-1b5b5c343581"
    record = {"workflow_id": workflow_id, "feature": "student-3"}
    client = coordinator_app.app.test_client()
    with patch.object(coordinator_app, "get_workflow", return_value=record), \
         patch.object(coordinator_app, "run_workflow", return_value=record) as run, \
         patch.object(coordinator_app, "record_decision") as decision:
        assert client.post("/workflow", json={"feature": "student-3", "user_request": "Aggregate counts"}).status_code == 403
        assert client.get(f"/workflow/{workflow_id}").status_code == 403
        assert client.post(f"/workflow/{workflow_id}/decision", json={"decision": "Approve"}).status_code == 403
        assert client.get("/workflow/status?feature=student-3").status_code == 403
        run.assert_not_called()
        decision.assert_not_called()
        headers = {"Authorization": f"Bearer {staff_token()}"}
        assert client.post("/workflow", json={"feature": "student-3", "user_request": "Aggregate counts"},
                           headers=headers).status_code == 200
        assert client.get(f"/workflow/{workflow_id}", headers=headers).status_code == 200


def test_azure_spec_references_private_review_key(monkeypatch):
    config = {"ENV_DOMAIN": "example.azurecontainerapps.io", "LOGIN_SERVER": "fixture.azurecr.io",
              "IMAGE_TAG": "a" * 40, "ENV_ID": "/fixture/environment", "PULL_ID": "/fixture/identity",
              "LOCATION": "australiaeast", "CUSTOMERS_REVIEW_SECRET": SECRET}
    for key, value in config.items():
        monkeypatch.setenv(key, value)
    for name in ("student3-backend", "shared-backend"):
        if name == "shared-backend":
            for key in ("SECRET_KEY", "STAFF_PASSWORD", "ORDERS_MCP_SECRET",
                        "ORDERS_CRUD_SECRET", "ORDERS_PURCHASE_SECRET"):
                monkeypatch.setenv(key, "fixture-value-at-least-32-characters")  # pragma: allowlist secret
        output = io.StringIO()
        with patch.object(sys, "argv", ["render", str(REPO / "scripts/deploy/apps.conf"), name]), redirect_stdout(output):
            load("student3_spec_" + name.replace("-", "_"), REPO / "scripts/deploy/render_app_spec.py")
        spec = json.loads(output.getvalue())
        env = spec["properties"]["template"]["containers"][0]["env"]
        assert {"name": "CUSTOMERS_REVIEW_SECRET", "secretRef": "customers-review-secret"} in env  # pragma: allowlist secret
        if name == "shared-backend":
            assert {"name": "CUSTOMERS_FRONTEND_ORIGIN", "value":
                    "https://student3-backend.example.azurecontainerapps.io"} in env
