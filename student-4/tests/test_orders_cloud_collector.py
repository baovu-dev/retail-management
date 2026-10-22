"""Mock-only cloud collection tests; synthetic fixtures are never deployment proof."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import sys
from types import ModuleType
from unittest.mock import Mock, patch

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("orders_cloud_collector_fixture", ROOT / "scripts/orders/cloud_evidence.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


@pytest.fixture
def setup(tmp_path):
    domain = "mockenv.australiaeast.azurecontainerapps.io"
    config = {"environment_domain": domain, "commit_sha": "a" * 40, "run_id": 39419555443,
              "frontend_origin": f"https://student4-frontend.{domain}", "api_origin": f"https://student4-backend.{domain}",
              "images": {name: "fixture.azurecr.io/student-4:aaaaaaa" for name in ("student4-frontend", "student4-backend")}}
    auth = {role: {"bearer_token": secrets.token_hex(24)} for role in ("owner", "other", "staff")}
    auth["owner"]["customer_id"], auth["other"]["customer_id"] = 900001, 900002
    calls, overrides = [], {}
    statuses = {"value": "PENDING"}
    item = {"product_id": 100001, "quantity": 1, "unit_price": 0.01}

    def send(method, url, **kwargs):
        calls.append((method, url, kwargs))
        token = kwargs["headers"].get("Authorization")
        code, body = 200, {}
        if url == config["frontend_origin"] + "/":
            body = '<title>My Orders</title><div id="orderDetail"></div><script>const API_BASE = ' + json.dumps(config["api_origin"]) + ';</script>'
        elif url.endswith("/api/health"):
            body = {"database_connected": True}
        elif url.endswith("/api/orders/count"):
            body = {"count": 0}
        elif method == "POST" and url.endswith("/api/orders"):
            if token == "Bearer " + auth["owner"]["bearer_token"]:
                code, body = 201, {"order_id": 77, "status": "PENDING"}
            else:
                code, body = 401, {"code": "unauthorized"}
        elif url.endswith("/api/orders/77"):
            if token == "Bearer " + auth["other"]["bearer_token"]:
                code, body = 403, {"code": "forbidden"}
            elif method == "GET":
                body = {"order_id": 77, "status": statuses["value"], "customer_id": auth["owner"]["customer_id"],
                        "items": [dict(item)], "total_amount": 0.01, "private_customer": "never serialize this"}
            else:
                statuses["value"] = "CANCELLED" if method == "DELETE" else "CONFIRMED"
                body = {"order_id": 77, "status": statuses["value"]}
        else:
            code, body = 403, {"code": "disabled"}
        custom = overrides.get((method, url))
        if custom:
            replacement = custom(code, body, kwargs)
            if isinstance(replacement, Exception):
                raise replacement
            code, body = replacement
        response = Mock(status_code=code, is_redirect=code in (301, 302, 303, 307, 308))
        response.headers = {"Content-Type": "text/html" if isinstance(body, str) and url.startswith(config["frontend_origin"]) else "application/json"}
        raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        response.iter_content.return_value = [raw]
        return response
    session = Mock()
    session.request.side_effect = send
    browser = Mock(return_value={"http_status": 200, "cors_allowed": True, "count": 0})
    resolve = Mock()
    run = collector.Collector(config, auth, 100001, Decimal("0.01"), tmp_path / "orders-cloud-evidence.json",
                              session=session, browser_probe=browser, resolve=resolve, delay=0)
    return run, config, auth, calls, overrides


def review_module():
    fake = ModuleType("ollama_client")
    fake.ask = Mock()
    spec = importlib.util.spec_from_file_location("orders_cloud_review_compat", ROOT / "ai-services/agentic-loop/modes/orders_cloud_review.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"ollama_client": fake}):
        spec.loader.exec_module(module)
    return module


def test_collection_records_authenticated_crud_denial_and_real_request_sequence(setup):
    run, config, auth, calls, _ = setup
    assert run.run()
    report = json.loads(run.output.read_text())
    assert review_module().behavior_checks(report)
    assert set(collector.CORE) <= set(report["checks"])
    assert report["collection_status"] == "complete"
    assert report["test_order_id"] == 77
    assert report["checks"]["ownership_denied"]["http_status"] == 403
    assert report["checks"]["read_after_cancel"]["observed"]["status"] == "CANCELLED"
    assert report["checks"]["read_after_cancel"]["observed"]["items_preserved"] is True
    assert report["checks"]["count"]["observed"]["count"] == 0
    for role in ("owner", "other", "staff"):
        assert auth[role]["bearer_token"] not in run.output.read_text()
    assert str(auth["owner"]["customer_id"]) not in run.output.read_text()
    assert "never serialize this" not in run.output.read_text()
    assert run.output.stat().st_mode & 0o077 == 0
    mutations = [(method, kwargs) for method, url, kwargs in calls if url.endswith("/api/orders/77") and method in ("PUT", "DELETE")]
    assert all(kwargs["headers"]["Authorization"] == "Bearer " + auth["staff"]["bearer_token"] for _, kwargs in mutations)
    created = [kwargs for method, url, kwargs in calls if method == "POST" and url.endswith("/api/orders") and kwargs["json"]]
    assert len(created) == 1
    assert created[0]["headers"]["Authorization"] == "Bearer " + auth["owner"]["bearer_token"]
    times = [datetime.fromisoformat(report["checks"][name]["timestamp"]) for name in collector.CORE]
    assert times == sorted(times)
    assert all(kwargs["verify"] is True and kwargs["allow_redirects"] is False for _, _, kwargs in calls)
    assert run.session.trust_env is False
    assert "not restart/redeployment" in report["limitations"][0]
    assert "never physically delete" in report["retention"]


@pytest.mark.parametrize("problem", ["legacy_400", "unauthenticated_201", "redirect", "timeout", "oversized", "bad_json"])
def test_fail_closed_before_authenticated_creation(setup, problem):
    run, config, _, calls, overrides = setup
    values = {"legacy_400": (400, {"error": "customer_id required"}), "unauthenticated_201": (201, {"order_id": 999}),
              "redirect": (302, {}), "timeout": requests.Timeout("Bearer do-not-log-exception"),
              "oversized": (401, {"private": "x" * collector.LIMIT}), "bad_json": (401, "not JSON")}
    overrides[("POST", config["api_origin"] + "/api/orders")] = lambda *args: values[problem]
    assert not run.run()
    assert not any(kwargs["json"] for method, url, kwargs in calls if method == "POST" and url.endswith("/api/orders"))
    report = json.loads(run.output.read_text())
    assert report["collection_status"] == "failed"
    assert not review_module().behavior_checks(report)
    assert "do-not-log-exception" not in run.output.read_text()


@pytest.mark.parametrize("code,body", [(200, {"customer_record": "PRIVATE DATA"}), (401, {"code": "unauthorized"}),
                                       (403, {"code": "disabled"}), (404, {"code": "not_found"})])
def test_ownership_failure_never_becomes_success_or_mutates_existing_order(setup, code, body):
    run, config, auth, calls, overrides = setup
    overrides[("GET", config["api_origin"] + "/api/orders/77")] = lambda status, data, kwargs: (
        (code, body) if kwargs["headers"].get("Authorization") == "Bearer " + auth["other"]["bearer_token"] else (status, data))
    assert not run.run()
    assert run.report["test_order_id"] == 77
    assert not any(method in {"PUT", "DELETE"} for method, _, _ in calls)
    assert "PRIVATE DATA" not in run.output.read_text()


@pytest.mark.parametrize("problem", ["wrong_owner", "wrong_id", "lost_items", "wrong_price", "lost_cancelled_status", "timeout_after_cancel"])
def test_order_identity_items_and_subsequent_retention_must_be_verified(setup, problem):
    run, config, auth, _, overrides = setup
    def change(status, data, kwargs):
        if kwargs["headers"].get("Authorization") != "Bearer " + auth["owner"]["bearer_token"]:
            return status, data
        if problem == "wrong_owner":
            data["customer_id"] = 123
        elif problem == "wrong_id":
            data["order_id"] = 999
        elif problem == "lost_items":
            data["items"] = []
        elif problem == "wrong_price":
            data["items"][0]["unit_price"] = 100.0
        elif data["status"] == "CANCELLED":
            if problem == "timeout_after_cancel":
                return requests.Timeout("private cancellation response")
            data["status"] = "CONFIRMED"
        return status, data
    overrides[("GET", config["api_origin"] + "/api/orders/77")] = change
    assert not run.run()
    assert run.report["collection_status"] == "failed"
    assert not review_module().behavior_checks(run.report)


def test_post_timeout_is_not_retried_and_partial_evidence_is_retained(setup):
    run, config, _, calls, overrides = setup
    def time_out(status, data, kwargs):
        return requests.Timeout("sensitive mutation exception") if kwargs["json"] else (status, data)
    overrides[("POST", config["api_origin"] + "/api/orders")] = time_out
    assert not run.run()
    assert len([kwargs for method, url, kwargs in calls if method == "POST" and url.endswith("/api/orders") and kwargs["json"]]) == 1
    assert run.report["test_order_id"] is None
    assert "reconciliation" in run.report["retention"]
    assert "sensitive mutation" not in run.output.read_text()


def test_missing_browser_cannot_be_replaced_by_an_origin_header(setup):
    run, _, _, calls, _ = setup
    run.browser_probe.side_effect = ImportError("playwright unavailable")
    assert not run.run()
    assert not any(method == "POST" for method, _, _ in calls)
    assert not run.report["checks"]["browser_api_access"]["passed"]


def test_cors_failure_blocks_mutation(setup):
    run, _, _, calls, _ = setup
    run.browser_probe.return_value = {"http_status": 200, "cors_allowed": False, "count": 0}
    assert not run.run()
    assert not any(method == "POST" for method, _, _ in calls)


def test_existing_evidence_is_never_overwritten(setup):
    run, _, _, calls, _ = setup
    run.output.write_text("keep original")
    with pytest.raises(FileExistsError):
        run.run()
    assert run.output.read_text() == "keep original"
    assert calls == []


@pytest.mark.parametrize("origin", ["http://localhost:5004", "https://127.0.0.1", "https://api.example", "https://student4-backend.fake.azurecontainerapps.io/?secret=value"])
def test_local_or_unrelated_origins_rejected_before_http(setup, origin):
    run, config, auth, calls, _ = setup
    config["api_origin"] = origin
    with pytest.raises(ValueError):
        collector.Collector(config, auth, 1, Decimal("0.01"), run.output)
    assert calls == []


def test_private_dns_and_image_mismatch_are_rejected(setup):
    run, config, _, calls, _ = setup
    with patch.object(socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
        with pytest.raises(ValueError):
            collector.public_dns((config["api_origin"],))
    config["images"]["student4-backend"] = "fixture.azurecr.io/student-4:bbbbbbb"
    with pytest.raises(ValueError):
        collector.validate_config(config)
    assert calls == []


def test_reviewer_rejects_failed_collector_extension_even_with_core_checks_passed(setup):
    run, _, _, _, _ = setup
    assert run.run()
    report = deepcopy(run.report)
    report["checks"]["ownership_denied"]["passed"] = False
    assert not review_module().behavior_checks(report)
    report = deepcopy(run.report)
    report["collection_status"] = "failed"
    assert not review_module().behavior_checks(report)


def test_credentials_require_private_file_distinct_identities_and_no_token_logging(setup, tmp_path):
    _, _, auth, _, _ = setup
    path = tmp_path / "private.json"
    path.write_text(json.dumps(auth))
    path.chmod(0o644)
    with pytest.raises(ValueError):
        collector.credentials(path)
    path.chmod(0o600)
    assert collector.credentials(path) == auth
    auth["other"]["customer_id"] = auth["owner"]["customer_id"]
    path.write_text(json.dumps(auth))
    with pytest.raises(ValueError):
        collector.credentials(path)


@pytest.mark.parametrize("name", ["ai_disabled", "mcp_disabled", "rag_disabled", "multi_agent_disabled"])
def test_enabled_flags_or_unrelated_success_are_not_cloud_baseline_proof(setup, name):
    run, config, _, _, overrides = setup
    overrides[("POST", config["api_origin"] + collector.CORE[name][1])] = lambda *args: (200, {"enabled": False})
    assert not run.run()
    assert not run.report["checks"][name]["passed"]
    assert not review_module().behavior_checks(run.report)


def test_current_orders_api_denies_anonymous_before_payload_validation(setup, monkeypatch):
    from test_backend import load_backend
    monkeypatch.setenv("ORDERS_CRUD_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("ORDERS_FRONTEND_ORIGIN", "http://localhost:3004")
    backend = load_backend()
    run, config, _, calls, overrides = setup
    downstream = Mock(status_code=400)
    downstream.json.return_value = {"error": "customer_id is required"}
    def actual_route(status, data, kwargs):
        with patch.object(backend, "db_post", return_value=downstream):
            response = backend.app.test_client().post("/api/orders", json=kwargs["json"], headers=kwargs["headers"])
        return response.status_code, response.json
    overrides[("POST", config["api_origin"] + "/api/orders")] = actual_route
    assert not run.run()
    assert run.report["checks"]["unauthenticated_create_denied"]["http_status"] == 401
    assert run.report["checks"]["invalid_credential_denied"]["http_status"] == 401
    assert run.report["checks"]["create"]["http_status"] == 401
    assert run.report["test_order_id"] is None
    assert not any(method in {"PUT", "DELETE"} for method, _, _ in calls)


def test_invalid_cloud_configuration_and_missing_mutation_consent_never_contact_http(setup, tmp_path, monkeypatch):
    _, config, auth, _, _ = setup
    deployed = tmp_path / "deployed.json"
    private = tmp_path / "private.json"
    deployed.write_text(json.dumps(config))
    private.write_text(json.dumps(auth))
    private.chmod(0o600)
    argv = ["cloud_evidence.py", "--deployment-file", str(deployed), "--credentials-file", str(private),
            "--product-id", "100001", "--unit-price", "0.01", "--output", str(tmp_path / "unused.json")]
    with patch.object(collector.requests, "Session") as session:
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit):
            collector.main()
        session.assert_not_called()
        config["api_origin"] = "http://localhost:5004"
        deployed.write_text(json.dumps(config))
        monkeypatch.setattr(sys, "argv", argv + ["--allow-test-order"])
        assert collector.main() == 1
        session.assert_not_called()
    assert not (tmp_path / "unused.json").exists()
