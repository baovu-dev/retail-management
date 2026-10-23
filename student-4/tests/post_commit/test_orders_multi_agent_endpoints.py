"""Two Orders backend API functions required by the Release 2 post-commit gate."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from itsdangerous import URLSafeTimedSerializer


TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS))
from test_backend import load_backend  # noqa: E402


SECRET = "orders-review-secret-with-at-least-32-characters"  # pragma: allowlist secret
SERVICE_KEY = "orders-service-key-with-at-least-32-characters"  # pragma: allowlist secret


def staff_token():
    return URLSafeTimedSerializer(SECRET, salt="orders-multi-agent-v1").dumps({
        "aud": "orders-multi-agent", "scope": "orders:workflow:review", "role": "staff",
        "staff_email": "staff@example.test",
    })


def configure(monkeypatch):
    monkeypatch.setenv("ORDERS_MCP_SECRET", SECRET)
    monkeypatch.setenv("MULTI_AGENT_ORDERS_SECRET", SERVICE_KEY)
    monkeypatch.setenv("MULTI_AGENT_ENABLED", "true")


def test_start_order_workflow_requires_staff_and_forces_orders_evidence(monkeypatch):
    configure(monkeypatch)
    backend = load_backend()
    client = backend.app.test_client()
    with patch("orders_multi_agent.requests.request") as call:
        assert client.post("/api/multi-agent/workflow").status_code == 401
        assert client.post("/api/multi-agent/workflow", headers={"Authorization": "Bearer forged"}).status_code == 401
        call.assert_not_called()
        call.return_value = Mock(status_code=202)
        call.return_value.json.return_value = {"status": "running", "workflow_id": "a16a1cef-507b-4dc5-9181-1b5b5c343581"}
        response = client.post("/api/multi-agent/workflow", json={"feature": "student-1", "user_request": "show customer 7"},
                               headers={"Authorization": f"Bearer {staff_token()}"})
    assert response.status_code == 202
    assert response.json["status"] == "running"
    args, kwargs = call.call_args
    assert args == ("POST", "http://localhost:8300/workflow?async=true")
    assert kwargs["json"]["feature"] == "student-4"
    assert "customer" not in kwargs["json"]["user_request"].lower() or "do not name customers" in kwargs["json"]["user_request"].lower()
    assert SECRET not in str(kwargs)
    assert kwargs["headers"] == {"X-Orders-Workflow-Key": SERVICE_KEY}


def test_record_order_decision_binds_staff_identity_and_blocks_other_features(monkeypatch):
    configure(monkeypatch)
    backend = load_backend()
    client = backend.app.test_client()
    workflow_id = "a16a1cef-507b-4dc5-9181-1b5b5c343581"
    path = f"/api/multi-agent/workflow/{workflow_id}/decision"
    headers = {"Authorization": f"Bearer {staff_token()}"}
    with patch("orders_multi_agent.requests.request") as call:
        assert client.post(path, json={"decision": "Approve"}).status_code == 401
        assert client.post(path, headers=headers, json={"decision": "wrong"}).status_code == 400
        call.assert_not_called()
        call.return_value = Mock(status_code=200)
        call.return_value.json.return_value = {"status": "awaiting_human_review", "feature": "student-1"}
        assert client.post(path, headers=headers, json={"decision": "Approve"}).status_code == 404
        assert call.call_count == 1
        call.return_value.json.side_effect = [
            {"status": "awaiting_human_review", "feature": "student-4"},
            {"status": "success", "human_decision": {"decision": "Reject"}},
        ]
        response = client.post(path, headers=headers, json={"decision": "Reject", "reviewer": "forged",
                                                       "comment": "Insufficient evidence."})
    assert response.status_code == 200
    assert response.json["human_decision"]["decision"] == "Reject"
    args, kwargs = call.call_args
    assert args == ("POST", f"http://localhost:8300/workflow/{workflow_id}/decision")
    assert kwargs["json"]["reviewer"] == "staff@example.test"
