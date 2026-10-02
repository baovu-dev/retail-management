"""Evidence-review integrity and preservation of the existing shared cases."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

LOOP = Path(__file__).resolve().parents[2] / "ai-services/agentic-loop"
sys.path.insert(0, str(LOOP))
from modes import orders_mode, mcp_mode, rag_mode
from test_orders_mcp import load_file


def sample():
    source = "knowledge/student-4/order-cancellation.md"
    evidence = {"cases": [
        {"id": key, "transport_ok": True, "response": {"answer": "Example answer.",
         "status": "success" if verdict == "supported" else "insufficient_context",
         "citations": [], "confidence_category": "Insufficient"},
         "retrieval": {"results": [{"source_id": source, "text": "Example source sentence.",
                                     "feature": "student-4", "distance": .2}]}}
        for key, _, verdict in orders_mode.CASES]}
    review = {"reviewer": "unit-test analyst fixture", "evidence_sha256": orders_mode.evidence_digest(evidence),
              "cases": [{"id": key, "verdict": verdict, "answer_quote": "Example answer.",
                         "grounds": [{"source_id": source, "quote": "Example source sentence."}],
                         "unsupported_claims": [], "rationale": "Test review fixture, not an actual model result."}
                        for key, _, verdict in orders_mode.CASES]}
    return evidence, review


def test_complete_bound_review():
    evidence, review = sample()
    assert orders_mode.assess_review(evidence, review)[0]


def test_citations_confidence_and_keywords_do_not_pass_without_review():
    evidence, _ = sample()
    evidence["cases"][0]["response"].update(answer="PENDING CONFIRMED CANCELLED CANCEL", confidence_category="High", citations=[{"ref": 1}])
    assert not orders_mode.assess_review(evidence, {})[0]


@pytest.mark.parametrize("change", ["tamper_answer", "missing_case", "wrong_verdict", "no_grounds", "fabricated_quote", "wrong_source", "unsupported_claim", "no_rationale", "transport_failed"])
def test_review_rejects_incomplete_or_unbound_claims(change):
    evidence, review = sample()
    case = review["cases"][0]
    if change == "tamper_answer":
        evidence["cases"][0]["response"]["answer"] = "A different actual answer"
    elif change == "missing_case":
        review["cases"].pop()
    elif change == "wrong_verdict":
        case["verdict"] = "contradiction"
    elif change == "no_grounds":
        case["grounds"] = []
    elif change == "fabricated_quote":
        case["grounds"][0]["quote"] = "Not present in the retrieved source"
    elif change == "wrong_source":
        case["grounds"][0]["source_id"] = "knowledge/student-1/review-policy.md"
    elif change == "unsupported_claim":
        case["unsupported_claims"] = ["Orders arrive tomorrow"]
    elif change == "no_rationale":
        case["rationale"] = ""
    else:
        evidence["cases"][0]["transport_ok"] = False
        review["evidence_sha256"] = orders_mode.evidence_digest(evidence)
    assert not orders_mode.assess_review(evidence, review)[0]


def test_existing_student1_cases_preserved():
    assert mcp_mode.EXPECTED_TOOLS == {"rating_summary", "reviews_by_product", "flagged_reviews"}
    assert len(mcp_mode.CHECKS) == 6
    assert rag_mode.FEATURE == "student-1"
    assert len(rag_mode.CHECKS) == 7
    assert any("product 103" in case[0] for case in rag_mode.CHECKS)


def test_collect_refuses_to_overwrite_saved_observations(tmp_path):
    path = tmp_path / "observations.json"
    path.write_text("preserve me")
    with pytest.raises(FileExistsError):
        orders_mode.run_rag(lambda *args: None, SimpleNamespace(review_file=None, evidence_file=path))
    assert path.read_text() == "preserve me"


def test_saved_review_has_no_network_calls(tmp_path, monkeypatch):
    import json
    evidence, review = sample()
    observed, reviewed = tmp_path / "observed.json", tmp_path / "review.json"
    observed.write_text(json.dumps(evidence))
    reviewed.write_text(json.dumps(review))
    def unexpected(*args, **kwargs):
        raise AssertionError("A saved review must not regenerate answers")
    monkeypatch.setattr(orders_mode.requests, "post", unexpected)
    assert orders_mode.run_rag(lambda *args: None, SimpleNamespace(review_file=reviewed, evidence_file=observed))


def test_unknown_question_cannot_pass_with_success_and_high_confidence():
    evidence, review = sample()
    evidence["cases"][-1]["response"].update(status="success", confidence_category="High")
    review["evidence_sha256"] = orders_mode.evidence_digest(evidence)
    assert not orders_mode.assess_review(evidence, review)[0]


@pytest.mark.parametrize("mode", ["mcp", "rag", "ai-mode"])
def test_cli_default_still_dispatches_existing_student1_modes(tmp_path, monkeypatch, mode):
    module = load_file("orders_agentic_main_test", "ai-services/agentic-loop/main.py")
    called = []
    monkeypatch.setitem(module.MODES, mode, lambda stage: called.append(mode) or True)
    monkeypatch.setattr(sys, "argv", ["main.py", "--mode", mode, "--output-dir", str(tmp_path)])
    assert module.main() == 0
    assert called == [mode]


def test_cli_orders_exception_exits_nonzero_without_secret(tmp_path, monkeypatch, capsys):
    module = load_file("orders_agentic_main_test", "ai-services/agentic-loop/main.py")
    def failed(*args):
        raise RuntimeError("private-auth-value")
    monkeypatch.setattr(orders_mode, "run", failed)
    monkeypatch.setattr(sys, "argv", ["main.py", "--mode", "mcp", "--feature", "student-4", "--output-dir", str(tmp_path)])
    assert module.main() == 1
    assert "private-auth-value" not in capsys.readouterr().out
    assert "private-auth-value" not in next(tmp_path.glob("*.txt")).read_text()
