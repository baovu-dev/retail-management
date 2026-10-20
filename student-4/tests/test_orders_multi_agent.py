"""Orders provider, staff capability and shared API fail-closed checks."""
import json
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import pytest

from test_orders_mcp import ORIGIN, SECRET, SESSION_SECRET, load_file


SERVICE_KEY = "orders-service-key-with-at-least-32-characters"  # pragma: allowlist secret
SERVER = Path(__file__).resolve().parents[2] / "ai-services" / "multi-agent-server"


def test_staff_issuer_rejects_customer_and_origin(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SESSION_SECRET)
    monkeypatch.setenv("ORDERS_MCP_SECRET", SECRET)
    monkeypatch.setenv("ORDERS_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("STAFF_PASSWORD", "private-staff-password")
    shared = load_file("shared_multi_agent_test", "shared/backend/app.py")
    with shared.app.test_client() as client:
        with client.session_transaction() as session:
            session["customer"] = {"customer_id": 7}
        assert client.post("/api/orders/multi-agent-token", headers={"Origin": ORIGIN}).status_code == 403
        with client.session_transaction() as session:
            session.clear()
            session["is_staff"] = True
            session["staff_email"] = "staff@example.test"
        assert client.post("/api/orders/multi-agent-token", headers={"Origin": "http://evil.example"}).status_code == 403
        result = client.post("/api/orders/multi-agent-token", headers={"Origin": ORIGIN})
        assert result.status_code == 200
        assert result.headers["Cache-Control"] == "no-store"
        token = result.json["access_token"]
    auth = load_file("orders_review_auth_test", "student-4/backend/orders_auth.py")
    assert auth.verify_review_token(token)[0]["staff_email"] == "staff@example.test"
    assert auth.verify_access_token(token, 1)[1][1] == 401


def test_public_evidence_is_only_aggregate_and_guidance():
    provider = load_file("orders_provider_test", "ai-services/multi-agent-server/evidence/student4_orders.py")
    response = Mock(status_code=200)
    response.json.return_value = {"count": 7, "customer_id": 42, "email": "secret@example.test"}
    with patch.object(provider.requests, "get", return_value=response):
        result = provider.collect("review the Orders rules")
    assert result["status"] == "success" and len(result["records"]) == 3
    assert result["records"][0]["text"] == "Total orders currently recorded: 7."
    assert "secret@example.test" not in str(result)
    assert "CANCELLED" in result["records"][1]["text"]


@pytest.mark.parametrize("body", [{"count": True}, {"count": "3"}, {"count": -1}, {"customer": []}])
def test_invalid_count_does_not_generate_evidence(body):
    provider = load_file("orders_provider_bad_test", "ai-services/multi-agent-server/evidence/student4_orders.py")
    response = Mock(status_code=200)
    response.json.return_value = body
    with patch.object(provider.requests, "get", return_value=response):
        assert provider.collect("review")["status"] == "error"


def test_orders_agent_prompts_only_name_available_evidence():
    planner = load_file("orders_planner_scope_test", "ai-services/multi-agent-server/agents/planner_agent.py")
    reviewer = load_file("orders_reviewer_scope_test", "ai-services/multi-agent-server/agents/reviewer_agent.py")
    answer = Mock(choices=[Mock(message=Mock(content="Reviewed"))])
    with patch.object(planner.client.chat.completions, "create", return_value=answer) as planning:
        planner.call_model("Review Orders", "student-4")
        orders_prompt = planning.call_args.kwargs["messages"][0]["content"]
        assert "CancellationRules table is not available" in orders_prompt
        assert "customer-specific count" in orders_prompt
        planner.call_model("Review Reviews", "student-1")
        assert "CancellationRules table is not available" not in planning.call_args.kwargs["messages"][0]["content"]
    with patch.object(reviewer.client.chat.completions, "create", return_value=answer) as reviewing:
        reviewer.call_model("Review Orders", "Plan", {"feature": "student-4", "evidence": []})
        assert "plan is not evidence" in reviewing.call_args.kwargs["messages"][0]["content"]
        reviewer.call_model("Review Reviews", "Plan", {"feature": "student-1", "evidence": []})
        assert "plan is not evidence" not in reviewing.call_args.kwargs["messages"][0]["content"]


def test_shared_server_requires_service_key_for_orders_only(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTI_AGENT_ORDERS_SECRET", SERVICE_KEY)
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.syspath_prepend(str(SERVER))
    import app as multi_agent_app
    import coordinator

    monkeypatch.setattr(coordinator, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(coordinator, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(multi_agent_app, "HISTORY_PATH", tmp_path / "history.jsonl")

    workflow_id = "a16a1cef-507b-4dc5-9181-1b5b5c343581"
    order = {"workflow_id": workflow_id, "feature": "student-4", "human_decision": {"status": "pending"}}
    client = multi_agent_app.app.test_client()
    with patch.object(multi_agent_app, "run_workflow", return_value=order) as run, \
         patch.object(multi_agent_app, "get_workflow", return_value=order), \
         patch.object(multi_agent_app, "record_decision") as decision:
        payload = {"feature": "student-4", "user_request": "Review Orders public rules"}
        assert client.post("/workflow", json=payload).status_code == 403
        assert client.get(f"/workflow/{workflow_id}").status_code == 403
        assert client.post(f"/workflow/{workflow_id}/decision", json={"decision": "Approve"}).status_code == 403
        assert client.get("/workflow/status?feature=student-4").status_code == 403
        run.assert_not_called()
        decision.assert_not_called()
        headers = {"X-Orders-Workflow-Key": SERVICE_KEY}
        assert client.post("/workflow", json=payload, headers=headers).status_code == 200
        assert client.get(f"/workflow/{workflow_id}", headers=headers).status_code == 200
        assert run.call_args.args == ("Review Orders public rules", "student-4")
        assert client.post("/workflow", json={"feature": "student-1", "user_request": "Reviews"}).status_code == 200


def test_three_agents_history_and_human_decision_use_real_public_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTI_AGENT_ORDERS_SECRET", SERVICE_KEY)
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.syspath_prepend(str(SERVER))
    import app as multi_agent_app
    import coordinator
    import evidence.student4_orders as provider
    import agents.worker_agent as worker

    monkeypatch.setattr(coordinator, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(coordinator, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(multi_agent_app, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(coordinator, "plan_workflow", lambda question, feature: {"status": "completed", "plan": "Use public evidence"})
    monkeypatch.setattr(worker, "call_model", lambda question, plan, evidence: "There are seven orders [orders count].")
    monkeypatch.setattr(coordinator, "review_output", lambda question, result, plan: {"status": "completed", "review": "Evidence checked"})
    count = Mock(status_code=200)
    count.json.return_value = {"count": 7, "customer_id": 8}
    headers = {"X-Orders-Workflow-Key": SERVICE_KEY}
    client = multi_agent_app.app.test_client()
    with patch.object(provider.requests, "get", return_value=count):
        created = client.post("/workflow", json={"feature": "student-4", "user_request": "Review Orders"}, headers=headers)
    assert created.status_code == 200
    workflow_id = created.json["workflow_id"]
    assert created.json["status"] == "awaiting_human_review"
    assert created.json["worker_result"]["evidence_count"] == 3
    assert client.get("/workflow/status?feature=student-4", headers=headers).json["workflow_history_count"] == 1
    assert client.get("/workflow/status?feature=student-4").status_code == 403
    assert client.get("/workflow/status").json["latest_workflow"] is None
    decided = client.post(f"/workflow/{workflow_id}/decision", headers=headers,
                          json={"decision": "Reject", "reviewer": "staff@example.test", "comment": "Needs rework"})
    assert decided.status_code == 200
    assert client.get(f"/workflow/{workflow_id}", headers=headers).json["status"] == "completed"
    assert client.post(f"/workflow/{workflow_id}/decision", headers=headers,
                       json={"decision": "Approve", "reviewer": "staff@example.test"}).status_code == 400
    history = (tmp_path / "history.jsonl").read_text()
    audit = (tmp_path / "audit.jsonl").read_text()
    assert SERVICE_KEY not in history + audit
    assert "staff@example.test" in history
    assert "planner_completed" in audit and "worker_completed" in audit and "reviewer_completed" in audit


def test_orders_workflow_returns_immediately_and_requires_key_while_running(monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_ORDERS_SECRET", SERVICE_KEY)
    import app as multi_agent_app

    started, release = Event(), Event()
    result = {"workflow_id": "", "feature": "student-4", "status": "awaiting_human_review"}

    def run(_request, _feature, *, workflow_id):
        result["workflow_id"] = workflow_id
        started.set()
        assert release.wait(timeout=3)
        return result

    monkeypatch.setattr(multi_agent_app, "run_workflow", run)
    monkeypatch.setattr(multi_agent_app, "get_workflow", lambda _id: result if release.is_set() else None)
    client = multi_agent_app.app.test_client()
    headers = {"X-Orders-Workflow-Key": SERVICE_KEY}
    created = client.post("/workflow?async=true", json={"feature": "student-4", "user_request": "Review Orders"},
                          headers=headers)
    assert created.status_code == 202
    workflow_id = created.json["workflow_id"]
    assert started.wait(timeout=3)
    assert client.get(f"/workflow/{workflow_id}").status_code == 403
    assert client.get(f"/workflow/{workflow_id}", headers=headers).status_code == 202
    release.set()
    multi_agent_app.ORDERS_JOBS[workflow_id].result(timeout=3)
    finished = client.get(f"/workflow/{workflow_id}", headers=headers)
    assert finished.status_code == 200 and finished.json["status"] == "awaiting_human_review"


def test_failed_reviewer_blocks_human_decision(monkeypatch, tmp_path):
    import coordinator

    monkeypatch.setattr(coordinator, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(coordinator, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(coordinator, "plan_workflow", lambda _request, _feature: {"status": "completed", "plan": "Plan"})
    monkeypatch.setattr(coordinator, "generate_output", lambda _request, _feature, _plan:
                        {"status": "completed", "output": "Evidence", "evidence_count": 3})
    monkeypatch.setattr(coordinator, "review_output", lambda _request, _result, _plan:
                        {"status": "error", "review": "", "error": "Reviewer model unavailable"})
    result = coordinator.run_workflow("Review Orders", "student-4")
    assert result["status"] == "error"
    assert result["human_decision"]["status"] == "blocked"
    assert coordinator.record_decision(result["workflow_id"], "Approve", "staff@example.test")["status"] == "error"
    assert "workflow_failed" in (tmp_path / "audit.jsonl").read_text()


def test_old_model_fallback_is_not_approvable(monkeypatch, tmp_path):
    import coordinator

    monkeypatch.setattr(coordinator, "HISTORY_PATH", tmp_path / "history.jsonl")
    workflow_id = "a16a1cef-507b-4dc5-9181-1b5b5c343581"
    (tmp_path / "history.jsonl").write_text(
        json.dumps({"workflow_id": workflow_id, "feature": "student-4",
                                 "status": "awaiting_human_review",
                                 "reviewer_result": {"review": "Risk: Review model unavailable."},
                                 "human_decision": {"status": "pending"}}) + "\n")
    assert coordinator.get_workflow(workflow_id)["status"] == "error"
    assert coordinator.record_decision(workflow_id, "Approve", "staff@example.test")["status"] == "error"
