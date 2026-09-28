from flask import Blueprint, render_template, request
import requests

from services.rag_api import RAG_FEATURE, call_rag_service, rag_disabled_response, rag_mode_is_enabled


rag_bp = Blueprint("rag_mode", __name__)

MAX_QUERY_LENGTH = 300


def _read_k():
    try:
        return max(1, min(int(request.form.get("k", "5")), 10))
    except ValueError:
        return 5


def _status_code(payload):
    # insufficient_context is a valid answer; only real errors are 500
    return 500 if payload.get("status") == "error" else 200

@rag_bp.get("/rag")
def rag_page():
    return render_template("rag.html")

@rag_bp.post("/rag/refresh")
def rag_refresh():
    if not rag_mode_is_enabled(request):
        return rag_disabled_response()

    try:
        payload = call_rag_service("/refresh", {})
        return payload, _status_code(payload)
    except requests.RequestException as exc:
        return {"status": "error", "error": f"Shared RAG server unreachable: {exc}"}, 503


@rag_bp.post("/rag/retrieve")
def rag_retrieve():
    if not rag_mode_is_enabled(request):
        return rag_disabled_response()

    query = request.form.get("query", "").strip()
    if not query:
        return {"status": "error", "error": "query is required"}, 400
    if len(query) > MAX_QUERY_LENGTH:
        return {"status": "error", "error": f"query must be under {MAX_QUERY_LENGTH} characters"}, 400

    try:
        payload = call_rag_service("/retrieve", {"query": query, "k": _read_k(), "feature": RAG_FEATURE})
        return payload, _status_code(payload)
    except requests.RequestException as exc:
        return {"status": "error", "error": f"Shared RAG server unreachable: {exc}"}, 503


@rag_bp.post("/rag/answer")
def rag_answer():
    if not rag_mode_is_enabled(request):
        return rag_disabled_response()

    query = request.form.get("query", "").strip()
    if not query:
        return {"status": "error", "error": "query is required"}, 400
    if len(query) > MAX_QUERY_LENGTH:
        return {"status": "error", "error": f"query must be under {MAX_QUERY_LENGTH} characters"}, 400

    try:
        payload = call_rag_service("/answer", {"query": query, "k": _read_k(), "feature": RAG_FEATURE})
        return payload, _status_code(payload)
    except requests.RequestException as exc:
        return {"status": "error", "error": f"Shared RAG server unreachable: {exc}"}, 503