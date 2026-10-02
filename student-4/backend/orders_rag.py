"""Orders documentation only, through the existing shared RAG HTTP contract."""
import os

from flask import Blueprint, jsonify, request
import requests

rag_bp = Blueprint("orders_rag", __name__)
FEATURE = "student-4"
INSUFFICIENT = "Insufficient context: the Orders documentation cannot answer this question."


def validate_answer(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid RAG response")
    if payload.get("status") == "insufficient_context":
        return {"status": "insufficient_context", "answer": INSUFFICIENT,
                "citations": [], "confidence_category": "Insufficient"}
    if payload.get("status") != "success":
        raise ValueError("Invalid RAG status")
    answer = payload.get("answer")
    citations = payload.get("citations")
    confidence = payload.get("confidence_category")
    if not isinstance(answer, str) or not answer.strip() or confidence not in ("High", "Medium", "Low"):
        raise ValueError("Invalid RAG answer")
    if not isinstance(citations, list) or not citations:
        raise ValueError("Missing citations")
    safe_citations = []
    for citation in citations:
        if not isinstance(citation, dict):
            raise ValueError("Invalid citation")
        source, chunk, ref = citation.get("source_id"), citation.get("chunk_id"), citation.get("ref")
        if (not isinstance(source, str) or not source.startswith("knowledge/student-4/")
                or not isinstance(chunk, str) or not chunk.startswith(source + "#")
                or type(ref) is not int or ref <= 0):
            raise ValueError("Citation outside Orders documentation")
        safe_citations.append({"ref": ref, "source_id": source, "chunk_id": chunk})
    return {"status": "success", "answer": answer, "citations": safe_citations,
            "confidence_category": confidence}


@rag_bp.post("/api/rag/answer")
def answer():
    if os.getenv("RAG_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return jsonify(status="error", code="disabled", error="RAG Mode is disabled."), 403
    data = request.get_json(silent=True)
    query = data.get("query") if isinstance(data, dict) else None
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 300:
        return jsonify(status="error", code="invalid_input", error="Enter a question of 1 to 300 characters."), 400
    k = data.get("k", 5)
    if type(k) is not int or not 1 <= k <= 10:
        return jsonify(status="error", code="invalid_input", error="k must be an integer from 1 to 10."), 400
    query = query.strip()
    try:
        response = requests.post(os.getenv("RAG_URL", "http://localhost:8200").rstrip("/") + "/answer",
                                 json={"query": query, "k": k, "feature": FEATURE}, timeout=(5, 120))
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("status") == "error":
            return jsonify(status="error", code="unavailable", error="Orders guide service is unavailable. Please try again."), 503
        result = validate_answer(payload)
    except requests.RequestException:
        return jsonify(status="error", code="unavailable", error="Orders guide service is unavailable. Please try again."), 503
    except (ValueError, TypeError):
        return jsonify(status="error", code="invalid_response", error="Orders guide returned an invalid response. Please try again."), 502
    return jsonify(**result, query=query, feature=FEATURE)
