import html
import json
import os
import requests
from flask import Blueprint, request, render_template
from services.rag_api import call_rag_service

rag_bp = Blueprint("rag_mode", __name__)

def rag_mode_is_enabled(req) -> bool:
    enabled = os.getenv(
        "RAG_ENABLED",
        "true"
    ).strip().lower() in (
        "1",
        "true",
        "yes",
        "on"
    )

    if not enabled:
        return False

    mode_header = req.headers.get(
        "X-RAG-Mode",
        "on"
    ).strip().lower()

    return mode_header in (
        "1",
        "true",
        "yes",
        "on"
    )

def rag_disabled_response():
    return "<p>RAG Mode is disabled.</p>", 403

def render_rag_answer(payload):
    status = payload.get("status", "unknown")
    answer = payload.get("answer", "")
    confidence = payload.get(
        "confidence_category",
        "Unknown"
    )
    citations = payload.get("citations", [])

    citation_html = ""

    if citations:
        items = []

        for citation in citations:
            source = html.escape(
                citation.get(
                    "source_id",
                    "Unknown source"
                )
            )

            items.append(
                f"<li>{source}</li>"
            )

        citation_html = (
            "<h4>Sources</h4>"
            "<ul>"
            + "".join(items)
            + "</ul>"
        )
    else:
        citation_html = (
            "<p><strong>Sources:</strong> None</p>"
        )

    return (
        f"<h3>RAG Answer</h3>"
        f"<p><strong>Status:</strong> "
        f"{html.escape(status)}</p>"
        f"<p><strong>Confidence:</strong> "
        f"{html.escape(confidence)}</p>"
        f"<p>{html.escape(answer)}</p>"
        f"{citation_html}"
    )

@rag_bp.get("/rag")
def rag_page():
    return render_template("rag.html")

@rag_bp.post("/rag/answer")
def rag_answer():
    if not rag_mode_is_enabled(request):
        return rag_disabled_response()

    query = request.form.get(
        "query",
        ""
    ).strip()

    if not query:
        return (
            "<p>Query is required.</p>",
            400
        )

    try:
        payload = call_rag_service(
            "/answer",
            {
                "query": query,
                "k": 5,
                "feature": "student-3"
            }
        )

        return render_rag_answer(payload), 200

    except requests.RequestException as exc:
        error = {
            "status": "error",
            "answer": (
                "Shared RAG server is unavailable."
            ),
            "confidence_category": "Unavailable",
            "citations": [],
            "detail": str(exc)
        }

        return render_rag_answer(error), 503