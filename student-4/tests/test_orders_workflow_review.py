"""Verify workflow review fails closed and cannot write human decisions."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def load_review():
    fake = ModuleType("ollama_client")
    fake.ask = lambda prompt, **kwargs: ("The human correction addresses the unsupported missing-count claim.", None)
    spec = importlib.util.spec_from_file_location("orders_workflow_review_fixture",
                                                 ROOT / "ai-services/agentic-loop/modes/orders_workflow_review.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"ollama_client": fake}):
        spec.loader.exec_module(module)
    return module


def fixture(module):
    workflow_id = "74574146-f23f-48ba-916e-d1a3a1c73ef1"
    human = {"status": "decided", "decision": "Correct", "reviewer": "staff@example.test",
             "comment": "Zero is evidence, not missing data.", "corrected_output": "There are zero recorded orders.",
             "decided_at": "2026-10-20T08:00:00+00:00"}
    evidence = [{"id": name, "text": "Published guidance."} for name in sorted(module.EXPECTED_IDS)]
    next(item for item in evidence if item["id"] == "orders count")["text"] = "Total orders currently recorded: 0."
    workflow = {"workflow_id": workflow_id, "feature": "student-4", "status": "completed",
                "user_request": "Review Orders guidance.",
                "planner_result": {"status": "completed", "plan": "Review aggregate and rules."},
                "worker_result": {"status": "completed", "output": "Count evidence missing.",
                                  "evidence_source": "orders-public-evidence", "evidence_count": 3, "evidence": evidence},
                "reviewer_result": {"status": "completed", "review": "Reject."}, "human_decision": human}
    history = [deepcopy(workflow), {"workflow_id": workflow_id, "record_type": "human_decision", "human_decision": deepcopy(human)}]
    audit = [{"workflow_id": workflow_id, "event": event, "timestamp": f"2026-10-20T07:00:0{index}+00:00",
              "feature": "student-4", "status": "completed", "evidence_count": 3}
             for index, event in enumerate(module.EVENTS)]
    audit[-1].update(decision="Correct", reviewer="staff@example.test")
    return workflow, history, audit


class OrdersWorkflowReviewTests(unittest.TestCase):
    def setUp(self):
        self.module = load_review()
        self.workflow, self.history, self.audit = fixture(self.module)

    def passes(self):
        return all(ok for _, ok in self.module.validate(self.workflow, self.history, self.audit))

    def test_zero_count_and_human_correction_preserve_valid_structure(self):
        self.assertTrue(self.passes())

    def test_missing_human_decision_is_not_complete(self):
        self.workflow["human_decision"] = {"status": "pending"}
        self.assertFalse(self.passes())

    def test_correct_requires_corrected_answer(self):
        self.workflow["human_decision"]["corrected_output"] = ""
        self.assertFalse(self.passes())

    def test_missing_source_fails(self):
        self.workflow["worker_result"]["evidence"].pop()
        self.assertFalse(self.passes())

    def test_negative_count_fails(self):
        next(item for item in self.workflow["worker_result"]["evidence"]
             if item["id"] == "orders count")["text"] = "Total orders currently recorded: -1."
        self.assertFalse(self.passes())

    def test_audit_order_matters(self):
        self.audit[1], self.audit[2] = self.audit[2], self.audit[1]
        self.assertFalse(self.passes())

    def test_changed_history_is_detected(self):
        self.history[0]["worker_result"]["output"] = "Different answer."
        self.assertFalse(self.passes())

    def test_legacy_fallback_is_not_completion(self):
        self.workflow["reviewer_result"]["review"] = "Review model unavailable"
        self.assertFalse(self.passes())

    def test_read_only_review_and_model_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            history, audit = root / "history.jsonl", root / "audit.jsonl"
            history.write_text("\n".join(json.dumps(row) for row in self.history))
            audit.write_text("\n".join(json.dumps(row) for row in self.audit))
            args = SimpleNamespace(workflow_id=self.workflow["workflow_id"], history_file=history,
                                   audit_file=audit, output_dir=root / "outputs")
            env = {"MULTI_AGENT_ORDERS_SECRET": secrets.token_hex(32), "MULTI_AGENT_URL": "http://localhost:8300"}
            good = Mock(status_code=200)
            good.json.return_value = self.workflow
            with patch.dict("os.environ", env), patch.object(self.module.requests, "get", side_effect=[good, Mock(status_code=403)]) as get:
                with patch.object(self.module.requests, "post") as post:
                    self.assertTrue(self.module.run(lambda *args: None, args))
                    post.assert_not_called()
                self.assertEqual(get.call_count, 2)
                self.assertNotIn("headers", get.call_args.kwargs)
            packet = json.loads(next(args.output_dir.glob("*.json")).read_text())
            self.assertIn("Human assessment required", packet["semantic_acceptance"])
            self.assertNotIn(env["MULTI_AGENT_ORDERS_SECRET"], json.dumps(packet))
            with patch.dict("os.environ", env), patch.object(self.module.requests, "get", side_effect=[good, Mock(status_code=403)]):
                with patch.object(self.module, "ask", return_value=(None, "timeout")):
                    self.assertFalse(self.module.run(lambda *args: None, args))


if __name__ == "__main__":
    unittest.main()
