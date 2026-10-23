import os
import uuid

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__, template_folder="templates", static_folder="css",
            static_url_path="/static")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/multi-agent")
def multi_agent():
    return render_template("multi_agent.html")


def forward_workflow(path):
    """Keep the internal Products backend address on the server side."""
    backend = os.getenv("API_BASE", "http://localhost:5002").rstrip("/")
    try:
        response = requests.post(f"{backend}{path}",
                                 json=request.get_json(silent=True) or {}, timeout=620)
        return jsonify(response.json()), response.status_code
    except requests.RequestException:
        return jsonify(error="Products workflow service unavailable"), 503
    except ValueError:
        return jsonify(error="Invalid Products workflow response"), 502


@app.post("/multi-agent/workflow")
def start_workflow():
    return forward_workflow("/multi-agent/workflow")


@app.post("/multi-agent/workflow/<workflow_id>/decision")
def decide_workflow(workflow_id):
    try:
        uuid.UUID(workflow_id)
    except ValueError:
        return jsonify(error="Invalid workflow ID"), 400
    return forward_workflow(f"/multi-agent/workflow/{workflow_id}/decision")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3002, debug=False)  # noqa: S104 - Docker ingress
