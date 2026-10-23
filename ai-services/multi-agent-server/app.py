import os
import hmac
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from flask import Flask, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from coordinator import HISTORY_PATH, get_workflow, read_jsonl, record_decision, run_workflow, workflow_status
from evidence import PROVIDERS


app = Flask(__name__)

MAX_REQUEST_LENGTH = 300
ORDERS_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orders-review")
ORDERS_JOBS = {}
ORDERS_JOBS_LOCK = Lock()


def orders_authorized():
    secret = os.getenv("MULTI_AGENT_ORDERS_SECRET", "")
    supplied = request.headers.get("X-Orders-Workflow-Key", "")
    return len(secret) >= 32 and hmac.compare_digest(supplied, secret)


def customers_authorized():
    secret = os.getenv("CUSTOMERS_REVIEW_SECRET", "")
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if len(secret) < 32 or scheme.lower() != "bearer" or not 0 < len(token) <= 4096:
        return False
    try:
        claims = URLSafeTimedSerializer(secret, salt="customers-review-v1").loads(token, max_age=120)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return False
    return (isinstance(claims, dict) and claims.get("iss") == "kicklab-shared"
            and claims.get("aud") == "customers-review" and claims.get("scope") == "customers:review"
            and claims.get("role") == "staff" and isinstance(claims.get("staff_email"), str)
            and bool(claims["staff_email"]))


def customers_guard(workflow_id):
    found = get_workflow(workflow_id)
    if found is not None and found.get("feature") == "student-3" and not customers_authorized():
        return jsonify({"status": "error", "error": "Customer workflow access denied"}), 403
    return None


def orders_guard(workflow_id):
    found = get_workflow(workflow_id)
    with ORDERS_JOBS_LOCK:
        pending = workflow_id in ORDERS_JOBS
    if (pending or found is not None and found.get("feature") == "student-4") and not orders_authorized():
        return jsonify({"status": "error", "error": "Orders workflow access denied"}), 403
    return None


@app.get("/")
def health():
    return jsonify({
        "service": "multi-agent-server",
        "status": "running",
        "features": sorted(PROVIDERS),
    })


@app.post("/workflow")
def workflow():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "invalid request"}), 400
    user_request = data.get("user_request")
    feature = data.get("feature", "student-1")
    if not isinstance(user_request, str) or not isinstance(feature, str):
        return jsonify({"status": "error", "error": "invalid request"}), 400
    user_request, feature = user_request.strip(), feature.strip()

    if not user_request:
        return jsonify({"status": "error", "error": "user_request is required"}), 400
    if len(user_request) > MAX_REQUEST_LENGTH:
        return jsonify({"status": "error", "error": f"user_request must be under {MAX_REQUEST_LENGTH} characters"}), 400
    if feature not in PROVIDERS:
        return jsonify({"status": "error", "error": f"unknown feature: {feature}"}), 400
    if feature == "student-4" and not orders_authorized():
        return jsonify({"status": "error", "error": "Orders workflow access denied"}), 403
    if feature == "student-3" and not customers_authorized():
        return jsonify({"status": "error", "error": "Customer workflow access denied"}), 403

    if feature == "student-4" and request.args.get("async") == "true":
        workflow_id = str(uuid.uuid4())
        with ORDERS_JOBS_LOCK:
            ORDERS_JOBS[workflow_id] = ORDERS_EXECUTOR.submit(
                run_workflow, user_request, feature, workflow_id=workflow_id)
        return jsonify({"status": "running", "workflow_id": workflow_id}), 202

    return jsonify(run_workflow(user_request, feature)), 200


@app.get("/workflow/status")
def status():
    feature = request.args.get("feature")
    if feature is not None:
        if feature not in PROVIDERS:
            return jsonify({"status": "error", "error": "unknown feature"}), 400
        if feature == "student-4" and not orders_authorized():
            return jsonify({"status": "error", "error": "Orders workflow access denied"}), 403
        if feature == "student-3" and not customers_authorized():
            return jsonify({"status": "error", "error": "Customer workflow access denied"}), 403
        matching = [record for record in read_jsonl(HISTORY_PATH)
                    if record.get("feature") == feature and record.get("record_type") != "human_decision"]
        return jsonify({"status": "success", "workflow_history_count": len(matching),
                        "latest_workflow": get_workflow(matching[-1]["workflow_id"]) if matching else None}), 200
    latest = workflow_status()
    if (latest.get("latest_workflow") or {}).get("feature") == "student-4" and not orders_authorized():
        # Preserve the existing Reviews status page without exposing an Orders review.
        reviews = [record for record in read_jsonl(HISTORY_PATH)
                   if record.get("feature") == "student-1" and record.get("record_type") != "human_decision"]
        latest["latest_workflow"] = get_workflow(reviews[-1]["workflow_id"]) if reviews else None
    if (latest.get("latest_workflow") or {}).get("feature") == "student-3" and not customers_authorized():
        latest["latest_workflow"] = None
    return jsonify(latest), 200


@app.get("/workflow/<workflow_id>")
def get_one(workflow_id):
    denied = customers_guard(workflow_id)
    if denied is not None:
        return denied
    denied = orders_guard(workflow_id)
    if denied is not None:
        return denied
    with ORDERS_JOBS_LOCK:
        job = ORDERS_JOBS.get(workflow_id)
    if job is not None:
        if not job.done():
            return jsonify({"status": "running", "workflow_id": workflow_id}), 202
        with ORDERS_JOBS_LOCK:
            ORDERS_JOBS.pop(workflow_id, None)
        try:
            job.result()
        except Exception:
            app.logger.exception("Orders review failed: %s", workflow_id)
            return jsonify({"status": "error", "error": "Orders workflow failed"}), 503
    found = get_workflow(workflow_id)
    if found is None:
        return jsonify({"status": "error", "error": "workflow not found"}), 404
    return jsonify(found), 200


@app.post("/workflow/<workflow_id>/decision")
def decision(workflow_id):
    denied = customers_guard(workflow_id)
    if denied is not None:
        return denied
    denied = orders_guard(workflow_id)
    if denied is not None:
        return denied
    data = request.get_json(silent=True) or {}
    result = record_decision(
        workflow_id,
        (data.get("decision") or "").strip(),
        (data.get("reviewer") or "").strip(),
        (data.get("comment") or "").strip(),
        data.get("corrected_output"),
    )
    if result["status"] == "success":
        return jsonify(result), 200
    code = 404 if result["error"] == "workflow not found" else 400
    return jsonify(result), code


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8300")), debug=debug_mode)  # noqa: S104 - must accept connections from Docker via host.docker.internal
