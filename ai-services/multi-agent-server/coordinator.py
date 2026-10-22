import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agents.planner_agent import plan_workflow
from agents.reviewer_agent import review_output
from agents.worker_agent import generate_output


BASE_DIR = Path(__file__).resolve().parent
HISTORY_PATH = BASE_DIR / "workflow_history.jsonl"
AUDIT_PATH = BASE_DIR / "coordination_audit.jsonl"

ALLOWED_DECISIONS = ["Approve", "Correct", "Partially Accept", "Reject"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def audit(workflow_id: str, event: str, details: Dict[str, Any]) -> None:
    append_jsonl(AUDIT_PATH, {"workflow_id": workflow_id, "timestamp": now_iso(), "event": event, **details})


def run_workflow(user_request: str, feature: str = "student-1",
                 workflow_id: str | None = None) -> Dict[str, Any]:
    start_time = time.time()
    workflow_id = workflow_id or str(uuid.uuid4())
    audit(workflow_id, "workflow_started", {"feature": feature, "user_request": user_request})

    # 1. Planner creates the plan
    planner_result = plan_workflow(user_request, feature)
    audit(workflow_id, "planner_completed", {"status": planner_result["status"]})

    worker_result = {"status": "skipped", "evidence": [], "evidence_count": 0,
                     "output": "", "error": "Planner did not complete"}
    reviewer_result = {"status": "skipped", "review": "", "error": "Worker did not complete"}
    if planner_result["status"] == "completed":
        # 2. Worker executes the plan using real feature evidence
        worker_result = generate_output(user_request, feature, planner_result["plan"])
        audit(workflow_id, "worker_completed", {
            "status": worker_result["status"],
            "evidence_count": worker_result.get("evidence_count", 0),
        })
        if worker_result["status"] == "completed":
            # 3. Reviewer checks output against the plan and evidence
            reviewer_result = review_output(user_request, worker_result, planner_result["plan"])
            audit(workflow_id, "reviewer_completed", {"status": reviewer_result["status"]})

    succeeded = all(result["status"] == "completed" for result in
                    (planner_result, worker_result, reviewer_result))

    duration_ms = int((time.time() - start_time) * 1000)

    workflow_result = {
        "status": "awaiting_human_review" if succeeded else "error",
        "workflow_id": workflow_id,
        "timestamp": now_iso(),
        "duration_ms": duration_ms,
        "feature": feature,
        "user_request": user_request,
        "participating_agents": ["planner_agent", "worker_agent", "reviewer_agent", "human_reviewer"],
        "planner_result": planner_result,
        "worker_result": worker_result,
        "reviewer_result": reviewer_result,
        "human_decision": {"required": succeeded, "status": "pending" if succeeded else "blocked",
                           "allowed_values": ALLOWED_DECISIONS},
    }

    append_jsonl(HISTORY_PATH, workflow_result)
    audit(workflow_id, "awaiting_human_review" if succeeded else "workflow_failed",
          {"duration_ms": duration_ms})
    return workflow_result


def get_workflow(workflow_id: str) -> Dict[str, Any] | None:
    workflow, decision = None, None
    for record in read_jsonl(HISTORY_PATH):
        if record.get("workflow_id") != workflow_id:
            continue
        if record.get("record_type") == "human_decision":
            decision = record
        else:
            workflow = record

    if workflow and not decision and workflow.get("status") == "awaiting_human_review":
        # Old synchronous runs stored model timeout text as if an agent had succeeded.
        # Preserve their original records, but never allow a human to approve them.
        legacy_fallback = any(marker in workflow.get(field, {}).get(text_field, "")
                              for field, text_field, marker in (
                                  ("planner_result", "plan", "Fallback Reason:"),
                                  ("worker_result", "output", "Model call failed"),
                                  ("reviewer_result", "review", "Review model unavailable")))
        if legacy_fallback:
            workflow = {**workflow, "status": "error", "error": "Agent model failed in this review",
                        "human_decision": {"required": False, "status": "blocked"}}
    if workflow and decision:
        workflow = {**workflow, "status": "completed", "human_decision": decision["human_decision"]}
    return workflow


def record_decision(workflow_id: str, decision: str, reviewer: str,
                    comment: str = "", corrected_output: str | None = None) -> Dict[str, Any]:
    if decision not in ALLOWED_DECISIONS:
        return {"status": "error", "error": f"decision must be one of {ALLOWED_DECISIONS}"}
    if not reviewer.strip():
        return {"status": "error", "error": "reviewer name is required"}

    workflow = get_workflow(workflow_id)
    if workflow is None:
        return {"status": "error", "error": "workflow not found"}
    if workflow["status"] != "awaiting_human_review":
        return {"status": "error", "error": "workflow is not ready for a human decision"}
    if workflow["human_decision"]["status"] == "decided":
        return {"status": "error", "error": "a decision has already been recorded for this workflow"}
    if decision == "Correct" and not (corrected_output or "").strip():
        return {"status": "error", "error": "corrected_output is required for a Correct decision"}

    human_decision = {
        "required": True,
        "status": "decided",
        "decision": decision,
        "reviewer": reviewer,
        "comment": comment,
        "corrected_output": corrected_output,
        "decided_at": now_iso(),
    }
    # Append a new record instead of editing the original, so history stays tamper-evident
    append_jsonl(HISTORY_PATH, {"record_type": "human_decision", "workflow_id": workflow_id,
                                "human_decision": human_decision})
    audit(workflow_id, "human_decision_recorded", {"decision": decision, "reviewer": reviewer})

    return {"status": "success", "workflow_id": workflow_id, "human_decision": human_decision}


def workflow_status() -> Dict[str, Any]:
    workflows = [r for r in read_jsonl(HISTORY_PATH) if r.get("record_type") != "human_decision"]
    latest = get_workflow(workflows[-1]["workflow_id"]) if workflows else None
    return {
        "status": "success",
        "workflow_history_count": len(workflows),
        "audit_record_count": len(read_jsonl(AUDIT_PATH)),
        "latest_workflow": latest,
    }


if __name__ == "__main__":
    result = run_workflow("Summarise customer feedback for product 103.")
    print(json.dumps(result, indent=2))
