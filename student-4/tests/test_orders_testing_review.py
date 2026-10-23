"""Orders testing-review completion must include actual checks and an AI review."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODE = ROOT / "ai-services/agentic-loop/modes/testing_mode.py"


class OrdersTestingReviewTests(unittest.TestCase):
    def run_review(self, *, scan_skip=False, review_error=False, endpoint_skip=False, feature="student-4"):
        fake = types.ModuleType("ollama_client")
        fake.ask = lambda prompt: (None, "timeout") if review_error else ("Review complete; human judgement required.", None)
        spec = importlib.util.spec_from_file_location("orders_testing_review_fixture", MODE)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"ollama_client": fake}):
            spec.loader.exec_module(module)
        calls = []

        def execute(command, **kwargs):
            calls.append((command, kwargs))
            if command[0] == "git":
                return 0, "student-4/backend/app.py\0student-4/tests/requirements.txt\0"
            if "pre_commit" in command:
                status = "Skipped" if scan_skip else "Passed"
                return 0, "\n".join(f"{hook}........{status}" for hook in module.HOOKS)
            if feature == "student-1":
                return 0, "::test_list_reviews PASSED\n::test_review_stats PASSED\n2 passed"
            status = "SKIPPED" if endpoint_skip else "PASSED"
            return 0, ("::test_start_order_workflow_requires_staff_and_forces_orders_evidence PASSED\n"
                       f"::test_record_order_decision_binds_staff_identity_and_blocks_other_features {status}\n"
                       "2 passed")

        with patch.object(module, "_run", side_effect=execute):
            passed = module.run(lambda *args: None, feature=feature)
        return passed, calls

    def test_orders_uses_own_tests_and_disables_external_services(self):
        passed, calls = self.run_review()
        self.assertTrue(passed)
        command, kwargs = calls[-1]
        self.assertIn("student-4/tests/post_commit", command)
        for key in ("AI_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED"):
            self.assertEqual(kwargs["env"][key], "false")
        self.assertIn("shared", calls[0][0])

    def test_orders_cannot_pass_when_review_is_unavailable(self):
        self.assertFalse(self.run_review(review_error=True)[0])

    def test_orders_cannot_pass_with_skipped_security_scans(self):
        self.assertFalse(self.run_review(scan_skip=True)[0])

    def test_orders_requires_both_named_endpoint_tests_to_pass(self):
        self.assertFalse(self.run_review(endpoint_skip=True)[0])

    def test_student1_keeps_existing_default_behavior(self):
        passed, calls = self.run_review(feature="student-1", review_error=True)
        self.assertTrue(passed)
        self.assertIn("student-1/tests/post_commit", calls[-1][0])


if __name__ == "__main__":
    unittest.main()
