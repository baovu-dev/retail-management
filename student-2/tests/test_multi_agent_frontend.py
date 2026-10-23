"""The public frontend relays workflow calls to the internal backend."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch


def frontend_app():
    path = Path(__file__).resolve().parents[1] / "frontend/app.py"
    spec = importlib.util.spec_from_file_location("student2_frontend", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_uses_internal_backend_and_preserves_result(monkeypatch):
    monkeypatch.setenv("API_BASE", "http://student2-backend:5002")
    module = frontend_app()
    client = module.app.test_client()
    upstream = Mock(status_code=200)
    upstream.json.return_value = {
        "workflow_id": "abc", "status": "awaiting_human_review"}
    with patch.object(module.requests, "post", return_value=upstream) as call:
        response = client.post("/multi-agent/workflow",
                               json={"user_request": "Review products"})
    assert response.status_code == 200
    assert response.json == upstream.json.return_value
    assert call.call_args.args[0] == "http://student2-backend:5002/multi-agent/workflow"


def test_decision_rejects_bad_id_without_upstream_call():
    module = frontend_app()
    client = module.app.test_client()
    with patch.object(module.requests, "post") as call:
        response = client.post("/multi-agent/workflow/../decision",
                               json={"decision": "Approve"})
        assert response.status_code in (400, 404)
        call.assert_not_called()


def test_browser_uses_same_origin():
    page = (Path(__file__).resolve().parents[1]
            / "frontend/templates/multi_agent.html").read_text()
    assert "fetch(path, options)" in page
    assert "location.hostname}:5002" not in page
