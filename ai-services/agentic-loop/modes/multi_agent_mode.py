"""Multi-Agent Review: runs a real workflow and checks agent order, evidence use, the human decision step and the audit trail."""
import json
import os
import time
from pathlib import Path

import requests

from ollama_client import ask

MULTI_AGENT_URL = os.getenv("MULTI_AGENT_URL", "http://localhost:8300")
REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_FILE = REPO_ROOT / "ai-services" / "multi-agent-server" / "coordination_audit.jsonl"
PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "multi_agent_review_prompt.txt"
FEATURE = "student-1"
REQUEST = "Summarise customer feedback for product 103."
EXPECTED_EVENTS = ["workflow_started", "planner_completed", "worker_completed",
                   "reviewer_completed", "awaiting_human_review", "human_decision_recorded"]


def _call(method, path, payload=None):
    response = requests.request(method, f"{MULTI_AGENT_URL}{path}", json=payload, timeout=180)
    return response.status_code, response.json()


def _audit_events(workflow_id):
    if not AUDIT_FILE.exists():
        return []
    events = []
    for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("workflow_id") == workflow_id:
                events.append(record.get("event"))
    return events


def run(stage):
    stage("PLAN", f"Workflow, human decision, boundary and audit checks against {MULTI_AGENT_URL}")
    results = []

    def check(description, ok, detail):
        stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} - {description} -> {detail}")
        results.append((description, bool(ok), detail))

    try:
        _call("GET", "/")
    except requests.RequestException as exc:
        stage("ADAPT", f"Multi-Agent server unreachable ({exc.__class__.__name__}), retrying once in 2s")
        time.sleep(2)
        try:
            _call("GET", "/")
        except requests.RequestException as exc:
            stage("ADAPT", f"FAIL: Multi-Agent server still unreachable ({exc.__class__.__name__})")
            return False

    worker, reviewer = {}, {}
    try:
        _, health = _call("GET", "/")
        check("Health: server running with the student-1 evidence provider",
              health.get("status") == "running" and FEATURE in health.get("features", []),
              f"features={health.get('features')}")

        stage("ACT", f"POST /workflow {REQUEST!r} (Planner -> Worker -> Reviewer)")
        code, workflow = _call("POST", "/workflow", {"user_request": REQUEST, "feature": FEATURE})
        workflow_id = workflow.get("workflow_id", "")
        planner = workflow.get("planner_result", {})
        worker = workflow.get("worker_result", {})
        reviewer = workflow.get("reviewer_result", {})
        decision = workflow.get("human_decision", {})

        check("Workflow pauses for human review", code == 200 and workflow.get("status") == "awaiting_human_review",
              f"status={workflow.get('status')} id={workflow_id}")
        check("All three agents completed in sequence",
              all(r.get("status") == "completed" for r in (planner, worker, reviewer)),
              f"planner={planner.get('status')} worker={worker.get('status')} reviewer={reviewer.get('status')}")
        check("Worker used real Reviews database evidence",
              worker.get("evidence_count", 0) > 0 and worker.get("evidence_source") == "reviews-db",
              f"evidence_count={worker.get('evidence_count')} source={worker.get('evidence_source')}")
        evidence_ids = [e["id"] for e in worker.get("evidence", [])]
        cited = [i for i in evidence_ids if i in (worker.get("output") or "")]
        check("Worker output cites its evidence IDs", bool(cited), f"cited={cited} of {evidence_ids}")
        check("Human decision is pending with four allowed values",
              decision.get("status") == "pending" and len(decision.get("allowed_values", [])) == 4,
              f"status={decision.get('status')} allowed={decision.get('allowed_values')}")

        stage("ACT", "Boundary requests")
        code, _ = _call("POST", "/workflow", {"user_request": "", "feature": FEATURE})
        check("Boundary: empty request is rejected", code == 400, f"HTTP {code}")
        code, _ = _call("POST", "/workflow", {"user_request": REQUEST, "feature": "student-99"})
        check("Boundary: unknown feature is rejected", code == 400, f"HTTP {code}")
        code, _ = _call("POST", f"/workflow/{workflow_id}/decision", {"decision": "Maybe", "reviewer": "agentic-loop-test"})
        check("Boundary: invalid decision value is rejected", code == 400, f"HTTP {code}")

        stage("ACT", "Recording a test decision (an automated validation run, not a real human review)")
        code, body = _call("POST", f"/workflow/{workflow_id}/decision",
                           {"decision": "Reject", "reviewer": "agentic-loop-test",
                            "comment": "Automated validation run, not a human review decision."})
        check("Decision is recorded", code == 200 and body.get("status") == "success", f"HTTP {code}")
        code, _ = _call("POST", f"/workflow/{workflow_id}/decision", {"decision": "Approve", "reviewer": "agentic-loop-test"})
        check("A recorded decision cannot be overwritten", code == 400, f"HTTP {code}")

        events = _audit_events(workflow_id)
        check("Audit trail records every coordination step in order", events == EXPECTED_EVENTS, f"events={events}")
    except Exception as exc:
        check("Validation run completed without errors", False, f"{exc.__class__.__name__}: {exc}")

    passed_count = sum(1 for _, ok, _ in results if ok)
    evidence = "\n".join(f"{'PASS' if ok else 'FAIL'}: {d} ({detail})" for d, ok, detail in results)
    evidence += f"\n\nWorker output:\n{worker.get('output')}\n\nReviewer assessment:\n{reviewer.get('review')}"

    stage("ADAPT", "Asking Ollama to review the evidence (advisory only, pass/fail comes from the checks)")
    review, error = ask(PROMPT_FILE.read_text(encoding="utf-8").format(evidence=evidence))
    if error:
        stage("ADAPT", f"Review skipped (Ollama error: {error})")
    else:
        for line in review.splitlines():
            if line.strip():
                stage("REVIEW", line.strip())

    stage("ADAPT", f"{passed_count}/{len(results)} checks passed")
    return passed_count == len(results)