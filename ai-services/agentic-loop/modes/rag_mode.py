import json
import os
import time
from pathlib import Path

import requests

from ollama_client import ask

RAG_URL = os.getenv("RAG_URL", "http://localhost:8200")
PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "rag_review_prompt.txt"
FEATURE = "student-1"


def _insufficient(code, r):
    return (r.get("status") == "insufficient_context"
            and r.get("citations") == []
            and r.get("confidence_category") == "Insufficient")


# (description, endpoint, payload, what a correct result looks like)
CHECKS = [
    ("Grounded: policy question answered with a citation", "/answer",
     {"query": "When does a review get flagged?"},
     lambda code, r: r.get("status") == "success" and "-0.8" in r.get("answer", "")
     and len(r.get("citations", [])) >= 1),
    ("Grounded: review question cites product 103 reviews", "/answer",
     {"query": "What do customers say about product 103?"},
     lambda code, r: r.get("status") == "success" and any(
         c["source_id"] in ("reviews-db:review/5", "reviews-db:review/6") for c in r.get("citations", []))),
    ("Confidence: grounded answer has a category", "/answer",
     {"query": "Can I review a product I did not buy?"},
     lambda code, r: r.get("confidence_category") in ("High", "Medium", "Low")),
    ("Retrieval: top result for 'product 103 reviews' is about product 103", "/retrieve",
     {"query": "product 103 reviews", "k": 5},
     lambda code, r: bool(r.get("results")) and "product 103" in r["results"][0]["text"]),
    ("Insufficient context: off-topic weather question", "/answer",
     {"query": "What is the weather in Sydney?"}, _insufficient),
    ("Insufficient context: off-topic tech support question", "/answer",
     {"query": "How do I reset my router?"}, _insufficient),
    ("Boundary: empty query is rejected", "/answer",
     {"query": ""},
     lambda code, r: code == 400 and r.get("status") == "error"),
]


def _post(path, payload):
    response = requests.post(f"{RAG_URL}{path}", json={**payload, "feature": FEATURE}, timeout=120)
    return response.status_code, response.json()


def _summary(r):
    if "results" in r:
        top = r["results"][0] if r["results"] else {}
        return f"top={top.get('source_id')} distance={top.get('distance')}"
    sources = [c["source_id"] for c in r.get("citations", [])]
    return (f"status={r.get('status')} confidence={r.get('confidence_category')} "
            f"sources={sources} answer={r.get('answer', r.get('error', ''))[:70]!r}")


def _health():
    requests.get(f"{RAG_URL}/health", timeout=5).raise_for_status()


def run(stage):
    stage("PLAN", f"{len(CHECKS)} checks against the shared RAG server at {RAG_URL}")

    try:
        _health()
    except requests.RequestException as exc:
        stage("ADAPT", f"RAG server unreachable ({exc.__class__.__name__}), retrying once in 2s")
        time.sleep(2)
        try:
            _health()
        except requests.RequestException as exc:
            stage("ADAPT", f"FAIL: RAG server still unreachable ({exc.__class__.__name__})")
            return False
    stage("OBSERVE", "RAG server health check passed")

    results = []
    for description, endpoint, payload, expectation in CHECKS:
        stage("ACT", f"POST {endpoint} {json.dumps(payload)}")
        try:
            code, body = _post(endpoint, payload)
            ok = bool(expectation(code, body))
            detail = _summary(body)
        except Exception as exc:
            ok, detail = False, f"request failed: {exc}"
        stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} - {description} -> {detail}")
        results.append((description, ok, detail))

    passed_count = sum(1 for _, ok, _ in results if ok)

    evidence = "\n".join(f"{'PASS' if ok else 'FAIL'}: {d} ({detail})" for d, ok, detail in results)
    stage("ADAPT", "Asking Ollama to review the evidence")
    review, error = ask(PROMPT_FILE.read_text(encoding="utf-8").format(evidence=evidence))
    if error:
        stage("ADAPT", f"Review skipped (Ollama error: {error})")
    else:
        for line in review.splitlines():
            if line.strip():
                stage("REVIEW", line.strip())

    stage("ADAPT", f"{passed_count}/{len(results)} checks passed")
    return passed_count == len(results)