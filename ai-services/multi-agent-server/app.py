import os

from flask import Flask, jsonify, request

from coordinator import get_workflow, record_decision, run_workflow, workflow_status
from evidence import PROVIDERS


app = Flask(__name__)

MAX_REQUEST_LENGTH = 300


@app.get("/")
def health():
    return jsonify({
        "service": "multi-agent-server",
        "status": "running",
        "features": sorted(PROVIDERS),
    })


@app.post("/workflow")
def workflow():
    data = request.get_json(silent=True) or {}
    user_request = (data.get("user_request") or "").strip()
    feature = (data.get("feature") or "student-1").strip()

    if not user_request:
        return jsonify({"status": "error", "error": "user_request is required"}), 400
    if len(user_request) > MAX_REQUEST_LENGTH:
        return jsonify({"status": "error", "error": f"user_request must be under {MAX_REQUEST_LENGTH} characters"}), 400
    if feature not in PROVIDERS:
        return jsonify({"status": "error", "error": f"unknown feature: {feature}"}), 400

    return jsonify(run_workflow(user_request, feature)), 200


@app.get("/workflow/status")
def status():
    return jsonify(workflow_status()), 200


@app.get("/workflow/<workflow_id>")
def get_one(workflow_id):
    found = get_workflow(workflow_id)
    if found is None:
        return jsonify({"status": "error", "error": "workflow not found"}), 404
    return jsonify(found), 200


@app.post("/workflow/<workflow_id>/decision")
def decision(workflow_id):
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