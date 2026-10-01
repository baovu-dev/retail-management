"""Answerability contract tests; model relevance still requires live claim review."""
import json
import sys
from unittest.mock import Mock, patch

import pytest
import requests

from test_orders_mcp import load_file


@pytest.fixture
def pipeline(monkeypatch):
    with patch.dict(sys.modules, {"chromadb": Mock()}):
        module = load_file("orders_evidence_pipeline_test", "ai-services/rag-server/rag_pipeline.py")
    monkeypatch.setattr(module, "append_audit", lambda *a: None)
    rows = [{"text": "No refund processing is implemented. Orders have three statuses.",
             "distance": .2, "source_id": "knowledge/student-4/scope.md",
             "chunk_id": "knowledge/student-4/scope.md#1", "authority_tier": "tier_2"}]
    monkeypatch.setattr(module, "retrieve_context", lambda *a: {"status": "success", "results": rows})
    return module


def model(pipeline, decision, coverage="complete"):
    response = Mock()
    response.json.return_value = {"response": json.dumps({"assessment": "Evidence assessment", "question_kind": "detail", **decision})}
    verification = Mock()
    verification.json.return_value = {"response": {"complete": "SUPPORTED", "missing": "INSUFFICIENT"}.get(coverage, coverage)}
    return patch.object(pipeline.requests, "post", side_effect=[response, verification])


def test_related_context_does_not_establish_answerability(pipeline):
    with model(pipeline, {"decision": "insufficient_context", "sentence_ids": []}):
        result = pipeline.answer_question("When will the payment arrive?", feature="student-4")
    assert result["status"] == "insufficient_context"
    assert result["citations"] == []
    assert result["confidence_category"] == "Insufficient"
    assert result["retrieval_summary"]["best_distance"] == .2


def test_implemented_question_can_use_negative_evidence(pipeline):
    quote = "No refund processing is implemented."
    with model(pipeline, {"decision": "answer", "sentence_ids": [1]}):
        result = pipeline.answer_question("Is refund processing implemented?", feature="student-4")
    assert result["status"] == "success"
    assert result["answer"] == quote + " [1]"
    assert len(result["citations"]) == 1


def test_real_quote_without_requested_fact_abstains(pipeline):
    with model(pipeline, {"decision": "answer", "sentence_ids": [1]}, coverage="missing"):
        result = pipeline.answer_question("When will the refund arrive?", feature="student-4")
    assert result["status"] == "insufficient_context"
    assert result["citations"] == []


def test_supported_no_is_not_missing_information(pipeline):
    with model(pipeline, {"question_kind": "yes_no", "decision": "answer", "sentence_ids": [1]}, coverage="NO"):
        result = pipeline.answer_question("Is refund processing implemented?", feature="student-4")
    assert result["status"] == "success"
    assert result["answer"] == "No refund processing is implemented. [1]"


def test_invalid_verifier_result_is_error(pipeline):
    with model(pipeline, {"decision": "answer", "sentence_ids": [1]}, coverage="unknown"):
        assert pipeline.answer_question("question", feature="student-4")["status"] == "error"


def test_verifier_transport_failure_is_error(pipeline):
    response = Mock()
    response.json.return_value = {"response": json.dumps({"assessment": "An explicit fact", "question_kind": "detail", "decision": "answer", "sentence_ids": [1]})}
    with patch.object(pipeline.requests, "post", side_effect=[response, requests.Timeout]):
        assert pipeline.answer_question("question", feature="student-4")["status"] == "error"


def test_two_model_calls_share_time_budget(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline.time, "monotonic", Mock(side_effect=[100, 100, 125]))
    with model(pipeline, {"decision": "answer", "sentence_ids": [1]}) as post:
        assert pipeline.answer_question("question", feature="student-4")["status"] == "success"
    assert [call.kwargs["timeout"] for call in post.call_args_list] == [90, 65]


def test_exhausted_model_budget_is_error(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline.time, "monotonic", Mock(side_effect=[100, 100, 191]))
    with model(pipeline, {"decision": "answer", "sentence_ids": [1]}) as post:
        assert pipeline.answer_question("question", feature="student-4")["status"] == "error"
    assert post.call_count == 1


@pytest.mark.parametrize("decision", [
    {}, {"answerable": "false", "sentence_ids": []},
    {"decision": "answer", "sentence_ids": []},
    {"decision": "insufficient_context", "sentence_ids": [1]},
    {"decision": "answer", "evidence": [{"ref": 1, "quote": "Refunds arrive tomorrow."}]},
    {"decision": "answer", "sentence_ids": [99]},
    {"decision": "answer", "sentence_ids": [True]},
    {"decision": "answer", "sentence_ids": [0]},
    {"decision": "answer", "sentence_ids": [-1]},
    {"decision": "answer", "sentence_ids": [1.0]},
    {"decision": "answer", "sentence_ids": ["1"]},
    {"decision": "answer", "sentence_ids": [1, 1]},
])
def test_invalid_model_response_is_error_not_abstention(pipeline, decision):
    with model(pipeline, decision):
        result = pipeline.answer_question("question", feature="student-4")
    assert result["status"] == "error"
    assert "answer" not in result


def test_model_outage_stays_error(pipeline):
    with patch.object(pipeline.requests, "post", side_effect=requests.Timeout):
        assert pipeline.answer_question("question", feature="student-4")["status"] == "error"


def test_sentence_id_maps_back_to_original_chunk(pipeline):
    with model(pipeline, {"decision": "answer", "sentence_ids": [2]}):
        result = pipeline.answer_question("How many statuses?", feature="student-4")
    assert result["answer"] == "Orders have three statuses. [1]"
    assert result["citations"][0]["ref"] == 1
    assert result["citations"][0]["chunk_id"] == "knowledge/student-4/scope.md#1"


def test_student1_generation_and_citation_behavior_preserved(pipeline):
    with patch.object(pipeline, "_generate", return_value=("Existing answer [1].", None)) as generate, \
            patch.object(pipeline, "_orders_evidence") as orders:
        result = pipeline.answer_question("review policy", feature="student-1")
    assert result["answer"] == "Existing answer [1]."
    assert result["status"] == "success"
    generate.assert_called_once()
    orders.assert_not_called()


def test_irrelevant_context_skips_model(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline, "retrieve_context", lambda *a: {"status": "success", "results": []})
    with patch.object(pipeline.requests, "post") as post:
        assert pipeline.answer_question("unrelated", feature="student-4")["status"] == "insufficient_context"
    post.assert_not_called()


def test_sentence_not_shown_to_model_is_rejected(pipeline, monkeypatch):
    rows = [{"text": " ".join(f"Fact number {i}." for i in range(1, 11))}]
    monkeypatch.setattr(pipeline, "embed_texts", lambda texts, **kw:
                        [[1, 0]] if len(texts) == 1 else [[i, 1] for i in range(1, 11)])
    with model(pipeline, {"decision": "answer", "sentence_ids": [9]}):
        evidence, error = pipeline._orders_evidence("question", rows)
    assert evidence is None and error


def test_sentence_embedding_outage_is_error(pipeline, monkeypatch):
    rows = [{"text": " ".join(f"Fact number {i}." for i in range(10))}]
    monkeypatch.setattr(pipeline, "embed_texts", Mock(side_effect=requests.Timeout))
    with patch.object(pipeline.requests, "post") as post:
        evidence, error = pipeline._orders_evidence("question", rows)
    assert evidence is None and error
    post.assert_not_called()


def test_ranked_id_maps_to_original_sentence_and_source(pipeline, monkeypatch):
    rows = [{"text": " ".join(f"Fact number {i}." for i in range(start, start + 5))}
            for start in (1, 6)]
    monkeypatch.setattr(pipeline, "embed_texts", lambda texts, **kw:
                        [[1, 0]] if len(texts) == 1 else [[i, 1] for i in range(1, 11)])
    with model(pipeline, {"decision": "answer", "sentence_ids": [1]}):
        evidence, error = pipeline._orders_evidence("question", rows)
    assert error is None
    assert evidence == [{"ref": 2, "quote": "Fact number 10."}]


def test_truncated_output_is_error_even_if_json_parses(pipeline):
    response = Mock()
    response.json.return_value = {"done_reason": "length", "response": json.dumps({
        "assessment": "Missing fact", "decision": "insufficient_context", "sentence_ids": []})}
    with patch.object(pipeline.requests, "post", return_value=response):
        assert pipeline.answer_question("question", feature="student-4")["status"] == "error"
