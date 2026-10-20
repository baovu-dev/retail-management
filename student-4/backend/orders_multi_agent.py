"""Staff review of public Orders evidence using the local shared agent service."""
import os
import uuid

from flask import Blueprint, jsonify, request
import requests

from orders_auth import bearer_token, verify_review_token


multi_agent_bp = Blueprint("orders_multi_agent", __name__)
PROMPT = ("Assess the current Orders status and cancellation rules against the live "
          "total order count. State only supported facts, cite the evidence IDs, "
          "and identify limitations. Do not name customers or individual orders.")
DECISIONS = {"Approve", "Correct", "Partially Accept", "Reject"}


def require_staff():
    if os.getenv("MULTI_AGENT_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return None, (jsonify(status="error", code="disabled", error="Multi-Agent mode is disabled."), 403)
    if len(os.getenv("MULTI_AGENT_ORDERS_SECRET", "")) < 32:
        return None, (jsonify(status="error", code="unavailable", error="Orders workflow is not configured."), 503)
    claims, error = verify_review_token(bearer_token(request))
    if error:
        return None, (jsonify(status="error", **error[0]), error[1])
    return claims, None


def workflow_id_valid(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def call_service(method, path, *, payload=None, timeout=10):
    base = os.getenv("MULTI_AGENT_SERVICE_URL", "http://localhost:8300").rstrip("/")
    headers = {"X-Orders-Workflow-Key": os.environ["MULTI_AGENT_ORDERS_SECRET"]}
    try:
        response = requests.request(method, f"{base}{path}", json=payload, headers=headers,
                                    timeout=timeout, allow_redirects=False)
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("invalid multi-agent response")
        if response.status_code in (200, 202, 400, 404):
            return jsonify(data), response.status_code
        return jsonify(status="error", code="unavailable", error="Orders workflow service unavailable."), 503
    except (requests.RequestException, ValueError):
        return jsonify(status="error", code="unavailable", error="Orders workflow service unavailable."), 503


@multi_agent_bp.post("/api/multi-agent/workflow")
def start_order_workflow():
    _, error = require_staff()
    if error:
        return error
    # No arbitrary user request, customer ID or bearer token goes into the shared audit log.
    return call_service("POST", "/workflow?async=true",
                        payload={"user_request": PROMPT, "feature": "student-4"})


@multi_agent_bp.get("/api/multi-agent/workflow/<workflow_id>")
def order_workflow(workflow_id):
    _, error = require_staff()
    if error:
        return error
    if not workflow_id_valid(workflow_id):
        return jsonify(status="error", code="invalid_input", error="Invalid workflow ID."), 400
    response, status = call_service("GET", f"/workflow/{workflow_id}")
    if status == 200 and response.get_json().get("feature") != "student-4":
        return jsonify(status="error", code="not_found", error="Orders workflow not found."), 404
    return response, status


@multi_agent_bp.get("/api/multi-agent/workflow/status")
def order_workflow_status():
    _, error = require_staff()
    if error:
        return error
    response, status = call_service("GET", "/workflow/status?feature=student-4")
    if status == 200 and (response.get_json().get("latest_workflow") or {}).get("feature") != "student-4":
        return jsonify(status="success", workflow_history_count=0, latest_workflow=None), 200
    return response, status


@multi_agent_bp.post("/api/multi-agent/workflow/<workflow_id>/decision")
def record_order_decision(workflow_id):
    claims, error = require_staff()
    if error:
        return error
    if not workflow_id_valid(workflow_id):
        return jsonify(status="error", code="invalid_input", error="Invalid workflow ID."), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", code="invalid_input", error="Decision is required."), 400
    decision, comment, corrected = data.get("decision"), data.get("comment", ""), data.get("corrected_output")
    if (not isinstance(decision, str) or decision not in DECISIONS
            or not isinstance(comment, str) or len(comment) > 500
            or corrected is not None and (not isinstance(corrected, str) or len(corrected) > 1000)
            or decision == "Correct" and not (corrected or "").strip()):
        return jsonify(status="error", code="invalid_input", error="Invalid review decision."), 400
    found, status = call_service("GET", f"/workflow/{workflow_id}")
    if status != 200:
        return found, status
    if found.get_json().get("feature") != "student-4":
        return jsonify(status="error", code="not_found", error="Orders workflow not found."), 404
    payload = {"decision": decision, "reviewer": claims["staff_email"],
               "comment": comment, "corrected_output": corrected}
    return call_service("POST", f"/workflow/{workflow_id}/decision", payload=payload)
