import sys
from unittest.mock import Mock, patch

import pytest
import requests

from test_backend import load_backend
from test_orders_mcp import load_file


def grounded():
    source = "knowledge/student-4/order-statuses.md"
    return {"status": "success", "answer": "Orders start as PENDING [1].",
            "confidence_category": "High", "citations": [
                {"ref": 1, "source_id": source, "chunk_id": source + "#1"}]}


@pytest.fixture
def rag(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    backend = load_backend()
    return backend.app.test_client(), sys.modules["orders_rag"]


def reply(payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    return response


def test_grounded_answer_and_feature_is_server_controlled(rag):
    client, module = rag
    with patch.object(module.requests, "post", return_value=reply(grounded())) as post:
        response = client.post("/api/rag/answer", json={"query": "  How do orders start?  ", "feature": "student-1"})
    assert response.status_code == 200
    assert response.json["feature"] == "student-4"
    assert response.json["answer"] == grounded()["answer"]
    assert response.json["confidence_category"] == "High"
    assert post.call_args.kwargs["json"] == {"query": "How do orders start?", "k": 5, "feature": "student-4"}
    assert post.call_args.kwargs["timeout"] == (5, 120)


@pytest.mark.parametrize("query", [None, "", "  ", 1, [], {}, "a" * 301])
def test_invalid_query_does_not_contact_rag(rag, query):
    client, module = rag
    with patch.object(module.requests, "post") as post:
        assert client.post("/api/rag/answer", json={"query": query}).status_code == 400
        post.assert_not_called()


@pytest.mark.parametrize("k", [True, 0, 11, "5", None])
def test_invalid_k(rag, k):
    client, module = rag
    with patch.object(module.requests, "post") as post:
        assert client.post("/api/rag/answer", json={"query": "status", "k": k}).status_code == 400
        post.assert_not_called()


def test_insufficient_context_is_not_service_failure(rag):
    client, module = rag
    with patch.object(module.requests, "post", return_value=reply({"status": "insufficient_context"})):
        response = client.post("/api/rag/answer", json={"query": "weather"})
    assert response.status_code == 200
    assert response.json["status"] == "insufficient_context"
    assert response.json["citations"] == []
    assert response.json["confidence_category"] == "Insufficient"


@pytest.mark.parametrize("exception", [requests.ConnectionError, requests.Timeout, requests.HTTPError])
def test_outage_has_no_fabricated_answer(rag, exception):
    client, module = rag
    with patch.object(module.requests, "post", side_effect=exception("private internal detail")):
        response = client.post("/api/rag/answer", json={"query": "status"})
    assert response.status_code == 503
    assert response.json["status"] == "error"
    assert "answer" not in response.json
    assert "private" not in response.text


def test_model_error_is_unavailable(rag):
    client, module = rag
    with patch.object(module.requests, "post", return_value=reply({"status": "error", "error": "Ollama unavailable"})):
        assert client.post("/api/rag/answer", json={"query": "status"}).status_code == 503


@pytest.mark.parametrize("payload", [None, [], {"status": "other"},
    {**grounded(), "citations": []}, {**grounded(), "answer": None},
    {**grounded(), "confidence_category": "99%"},
    {**grounded(), "citations": [{"ref": 1, "source_id": "knowledge/student-1/policy.md", "chunk_id": "knowledge/student-1/policy.md#1"}]}])
def test_invalid_or_cross_feature_response_fails_closed(rag, payload):
    client, module = rag
    with patch.object(module.requests, "post", return_value=reply(payload)):
        response = client.post("/api/rag/answer", json={"query": "status"})
    assert response.status_code == 502
    assert "answer" not in response.json


def test_disabled_by_default(rag, monkeypatch):
    client, module = rag
    monkeypatch.delenv("RAG_ENABLED")
    with patch.object(module.requests, "post") as post:
        assert client.post("/api/rag/answer", json={"query": "status"}).status_code == 403
        post.assert_not_called()


def test_existing_loader_supports_orders_and_retains_reviews(monkeypatch):
    # CI needs neither Chroma installed nor a running embedding service.
    with patch.dict(sys.modules, {"chromadb": Mock()}):
        pipeline = load_file("orders_rag_pipeline_test", "ai-services/rag-server/rag_pipeline.py")
    chunks = pipeline.load_knowledge_chunks()
    assert {"student-1", "student-4"}.issubset({c["feature"] for c in chunks})
    orders = [c for c in chunks if c["feature"] == "student-4"]
    assert len({c["source_id"] for c in orders}) == 4
    assert all(c["source_id"].startswith("knowledge/student-4/") for c in orders)
    collection = Mock()
    collection.query.return_value = {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}
    monkeypatch.setattr(pipeline, "get_collection", lambda: collection)
    monkeypatch.setattr(pipeline, "embed_texts", lambda *args, **kwargs: [[0.1]])
    monkeypatch.setattr(pipeline, "append_audit", lambda *args: None)
    assert pipeline.retrieve_context("status", feature="student-4")["status"] == "success"
    assert collection.query.call_args.kwargs["where"] == {"feature": "student-4"}
