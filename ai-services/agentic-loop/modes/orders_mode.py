"""Opt-in Orders cases; the existing Student 1 validation modes are unchanged.

RAG transport success is not a correctness verdict. Save full answers and retrieved
text, then require an explicit analyst review bound to those exact observations.
Reviewing a saved run never repeats generation or modifies a RAG index.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import requests
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from modes.mcp_mode import EXPECTED_TOOLS, _extract

CASES = [
    ("statuses", "What are the three supported order statuses?", "supported"),
    ("confirmed_cancel", "Can a CONFIRMED order be cancelled?", "supported"),
    ("records", "After cancellation, are the order record and its items preserved or deleted?", "supported"),
    ("delivery_unknown", "Exactly what date will my CONFIRMED order be delivered?", "correct_abstention"),
    ("refund_unknown", "How many business days after cancelling my CONFIRMED order will the refund reach my bank?", "correct_abstention"),
]


def evidence_digest(evidence):
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def assess_review(evidence, review):
    """Check review completeness/provenance, not semantic truth via word matching.

The analyst must compare the entire answer (including contradictions/unsupported
extra claims) to the retrieved text. PASS here means that explicit review passes,
not that citations or confidence automatically establish correctness.
"""
    if review.get("evidence_sha256") != evidence_digest(evidence) or not review.get("reviewer"):
        return False, ["Review missing or does not match this exact evidence"]
    cases = evidence.get("cases", [])
    decisions = review.get("cases", [])
    if {c.get("id") for c in cases} != {c[0] for c in CASES} or len(cases) != len(CASES):
        return False, ["Incomplete evidence"]
    if {c.get("id") for c in decisions} != {c[0] for c in CASES} or len(decisions) != len(CASES):
        return False, ["Incomplete review"]
    messages = []
    passed = True
    for case in cases:
        decision = next(r for r in decisions if r["id"] == case["id"])
        expected = next(c[2] for c in CASES if c[0] == case["id"])
        answer = case["response"].get("answer", "")
        quote = decision.get("answer_quote")
        grounds = decision.get("grounds", [])
        ok = (case.get("transport_ok") is True and decision.get("verdict") == expected
              and isinstance(quote, str) and bool(quote) and quote in answer
              and decision.get("unsupported_claims") == []
              and bool(decision.get("rationale")) and bool(grounds))
        if expected == "correct_abstention":
            ok = (ok and case["response"].get("status") == "insufficient_context"
                  and case["response"].get("citations") == []
                  and case["response"].get("confidence_category") == "Insufficient")
        else:
            ok = ok and case["response"].get("status") == "success"
        for ground in grounds:
            ok = ok and any(
                r["source_id"] == ground.get("source_id")
                and isinstance(ground.get("quote"), str) and bool(ground["quote"])
                and ground["quote"] in r["text"]
                and r["feature"] == "student-4" and r["distance"] <= 0.40
                for r in case["retrieval"].get("results", []))
        messages.append(f"{'PASS' if ok else 'FAIL'} analyst claim review {case['id']}: {decision.get('verdict')} — {decision.get('rationale', '')}")
        passed = passed and bool(ok)
    return passed, messages


def run_rag(stage, args):
    if args.review_file:
        stage("PLAN", "Review saved actual RAG observations; no network calls or index refresh")
        evidence = json.loads(args.evidence_file.read_text())
        review = json.loads(args.review_file.read_text())
        passed, messages = assess_review(evidence, review)
        for message in messages:
            stage("REVIEW", message)
        return passed
    if args.evidence_file.exists():
        raise FileExistsError("Use a new evidence filename; previous observations are immutable")
    rag_url = os.getenv("RAG_URL", "http://localhost:8200").rstrip("/")
    orders_url = os.getenv("ORDERS_API_URL", "http://localhost:5004").rstrip("/")
    stage("PLAN", "Collect five Orders answers and full search grounds; correctness requires an analyst review")
    evidence = {"feature": "student-4", "created_at": datetime.now(timezone.utc).isoformat(),
                "rag_url": rag_url, "orders_url": orders_url, "cases": []}
    args.evidence_file.parent.mkdir(parents=True, exist_ok=True)
    for case_id, query, _ in CASES:
        stage("ACT", f"{case_id}: retrieve student-4 context, then ask via Orders backend")
        retrieved = requests.post(rag_url + "/retrieve", json={"query": query, "feature": "student-4", "k": 5}, timeout=130)
        retrieved.raise_for_status()
        retrieval = retrieved.json()
        response = requests.post(orders_url + "/api/rag/answer", json={"query": query, "k": 5}, timeout=130)
        body = response.json()
        rows = retrieval.get("results", [])
        ok = (response.status_code == 200 and retrieval.get("status") == "success"
              and bool(rows) and all(r.get("feature") == "student-4" for r in rows)
              and body.get("status") in {"success", "insufficient_context"}
              and isinstance(body.get("answer"), str) and bool(body["answer"].strip()))
        evidence["cases"].append({"id": case_id, "query": query, "http": response.status_code,
                                  "transport_ok": ok, "response": body, "retrieval": retrieval})
        args.evidence_file.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
        stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} transport {case_id}; semantic correctness UNREVIEWED")
        stage("OBSERVE", json.dumps({"answer": body.get("answer"), "grounds": rows}, ensure_ascii=False))
    stage("ADAPT", "REVIEW_REQUIRED: compare every factual claim against saved grounds; do not use confidence as correctness")
    # Deliberately nonzero until the captured answers have been reviewed.
    return False


async def run_mcp_checks(stage, runtime):
    shared = os.getenv("SHARED_URL", "http://localhost:5000").rstrip("/")
    orders = os.getenv("ORDERS_API_URL", "http://localhost:5004").rstrip("/")
    origin = os.getenv("ORDERS_FRONTEND_ORIGIN", "http://localhost:3004")
    browser_session = requests.Session()
    login = browser_session.post(shared + "/login", data={"email": runtime["email"], "password": runtime["password"]}, timeout=10)
    login.raise_for_status()
    if "session" not in browser_session.cookies:
        raise RuntimeError("Shared login failed")

    def token(order_id):
        response = browser_session.post(shared + "/api/orders/mcp-token", json={"order_id": order_id},
                                        headers={"Origin": origin}, timeout=10)
        response.raise_for_status()
        return response.json()["access_token"]

    own, other = runtime["order_id"], runtime["other_order_id"]
    own_token, other_token = token(own), token(other)
    checks = [
        ("owned order", own, own_token, lambda r: r == {"order_id": own, "status": "PENDING"}),
        ("other customer denied at direct MCP", other, other_token, lambda r: r.get("code") == "forbidden"),
        ("invalid ID rejected", -1, own_token, lambda r: r.get("code") == "invalid_input"),
        ("forged token denied", own, "forged", lambda r: r.get("code") == "unauthorized"),
    ]
    results = []
    async with streamablehttp_client(os.getenv("MCP_URL", "http://localhost:8100/mcp")) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            registered = {t.name for t in (await session.list_tools()).tools}
            registry_ok = (EXPECTED_TOOLS | {"get_order_status"}).issubset(registered)
            stage("OBSERVE", f"{'PASS' if registry_ok else 'FAIL'} existing Reviews and Orders tool registry: {sorted(registered)}")
            results.append(registry_ok)
            for name, order_id, access_token, expected in checks:
                stage("ACT", name + " (authentication omitted)")
                result = _extract(await session.call_tool("get_order_status", {"order_id": order_id, "access_token": access_token}))
                ok = bool(expected(result))
                safe = {k: result[k] for k in ("order_id", "status", "code") if k in result}
                stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} {name}: {json.dumps(safe)}")
                results.append(ok)
    response = requests.post(orders + "/api/mcp/order-status", json={"order_id": own},
                             headers={"Authorization": "Bearer " + own_token}, timeout=30)
    body = response.json()
    ok = (response.status_code == 200 and body.get("order_id") == own and body.get("status") == "PENDING"
          and body.get("source") == "mcp" and body.get("tool") == "get_order_status")
    stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} Orders backend to actual MCP")
    results.append(ok)
    stage("ADAPT", f"{sum(results)}/{len(results)} Orders MCP checks passed; no writes requested")
    return all(results)


def run(stage, args):
    if args.mode == "rag":
        return run_rag(stage, args)
    stage("PLAN", "Orders MCP with existing private test credentials; preserve Student 1 tools")
    runtime = json.loads((Path(os.environ["ORDERS_VALIDATION_RUN"]) / "runtime.json").read_text())
    return asyncio.run(run_mcp_checks(stage, runtime))
