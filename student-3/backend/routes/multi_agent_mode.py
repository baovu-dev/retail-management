"""Staff-only Customer aggregate review endpoints."""

import os
import uuid

import requests
from flask import Blueprint, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

multi_agent_bp = Blueprint("multi_agent_mode", __name__)
FEATURE = "student-3"
QUESTION = "Review the current aggregate customer account count and status counts. Do not discuss individual accounts."


def enabled():
    return os.getenv("MULTI_AGENT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def authenticated_staff():
    secret = os.getenv("CUSTOMERS_REVIEW_SECRET", "")
    if len(secret) < 32:
        return None, ({"error": "Customer review authentication unavailable."}, 503)
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not 0 < len(token) <= 4096:
        return None, ({"error": "Staff authentication required."}, 401)
    try:
        claims = URLSafeTimedSerializer(secret, salt="customers-review-v1").loads(token, max_age=120)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None, ({"error": "Staff authentication required."}, 401)
    if (not isinstance(claims, dict) or claims.get("iss") != "kicklab-shared"
            or claims.get("aud") != "customers-review" or claims.get("scope") != "customers:review"
            or claims.get("role") != "staff" or not isinstance(claims.get("staff_email"), str)
            or not claims["staff_email"]):
        return None, ({"error": "Staff authentication required."}, 401)
    return claims["staff_email"], None


def service_request(method, path, **kwargs):
    try:
        kwargs.setdefault("headers", {"Authorization": request.headers.get("Authorization", "")})
        response = requests.request(method, f"{os.getenv('MULTI_AGENT_SERVICE_URL', 'http://localhost:8300')}{path}",
                                    timeout=120 if method == "POST" and path == "/workflow" else 10, **kwargs)
        return response.json(), response.status_code
    except (requests.RequestException, ValueError):
        return {"error": "Multi-Agent service unavailable."}, 503


def require_staff():
    if not enabled():
        return None, ({"error": "Multi-Agent mode is disabled."}, 403)
    return authenticated_staff()


@multi_agent_bp.get("/multi-agent")
def multi_agent_page():
    return render_template("multi_agent.html", shared_url=os.getenv("SHARED_URL", "http://localhost:5000"))


@multi_agent_bp.post("/multi-agent/workflow")
def multi_agent_workflow():
    _, error = require_staff()
    if error:
        return error
    # Never forward browser-controlled text into the planner prompt or workflow history.
    return service_request("POST", "/workflow", json={"feature": FEATURE, "user_request": QUESTION})


@multi_agent_bp.post("/multi-agent/workflow/<workflow_id>/decision")
def multi_agent_decision(workflow_id):
    reviewer, error = require_staff()
    if error:
        return error
    try:
        uuid.UUID(workflow_id)
    except ValueError:
        return {"error": "Invalid workflow ID."}, 400
    workflow, status = service_request("GET", f"/workflow/{workflow_id}")
    if status != 200 or not isinstance(workflow, dict) or workflow.get("feature") != FEATURE:
        return {"error": "Customer workflow not found."}, 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("decision") not in {"Approve", "Partially Accept", "Correct", "Reject"}:
        return {"error": "Invalid decision."}, 400
    payload = {"decision": data["decision"], "reviewer": reviewer,
               "comment": data.get("comment"), "corrected_output": data.get("corrected_output")}
    return service_request("POST", f"/workflow/{workflow_id}/decision", json=payload)


@multi_agent_bp.get("/multi-agent/workflow/status")
def multi_agent_workflow_status():
    _, error = require_staff()
    if error:
        return error
    return service_request("GET", "/workflow/status?feature=student-3")
