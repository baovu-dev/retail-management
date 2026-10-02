"""Opt-in real shared RAG + Docker Orders + Chrome validation (public docs only)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright, expect
import requests

from validation_checks import result_exit_code, route_resource

RUN = Path(os.environ["ORDERS_VALIDATION_RUN"]).resolve()
ROOT = Path(__file__).resolve().parents[2]
RAG = "http://localhost:8200"
QUESTION = "What are the three supported order statuses?"
report = []
os.umask(0o077)


def record(name, ok, detail):
    report.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    (RUN / "rag-results.json").write_text(json.dumps(report, indent=2))
    print(report[-1]["result"], name, detail, flush=True)
    if not ok:
        raise RuntimeError(name)


def post(path, payload):
    response = requests.post(RAG + path, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def ask(page, query):
    page.locator("#ragQuery").fill(query)
    with page.expect_response(lambda r: "/api/rag/answer" in r.url, timeout=135000) as captured:
        page.get_by_role("button", name="Ask Orders guide", exact=True).click()
    expect(page.locator("#ragButton")).to_be_enabled(timeout=135000)
    return captured.value.status, captured.value.json()


try:
    if (RUN / "rag-results.json").exists():
        (RUN / f"rag-attempt-{int(time.time())}.json").write_text((RUN / "rag-results.json").read_text())
    record("RAG health", requests.get(RAG + "/health", timeout=5).status_code == 200, "local shared RAG")
    refreshed = post("/refresh", {})
    record("corpus refresh", refreshed.get("status") == "success", refreshed)
    retrieval = post("/retrieve", {"query": QUESTION, "feature": "student-4", "k": 5})
    rows = retrieval.get("results", [])
    record("student-4 retrieval", bool(rows) and all(r["feature"] == "student-4" for r in rows),
           [{"source": r["source_id"], "distance": r["distance"]} for r in rows])
    reviews = post("/retrieve", {"query": "When does a review get flagged?", "feature": "student-1", "k": 3})
    record("student-1 docs preserved", bool(reviews.get("results")) and all(r["feature"] == "student-1" for r in reviews["results"]),
           [r["source_id"] for r in reviews.get("results", [])])
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        context.route("**/*", route_resource)
        page = context.new_page()
        # Keep screenshots scoped to test-customer orders; credentials are never displayed.
        runtime = json.loads((RUN / "runtime.json").read_text())
        page.goto(f"http://localhost:3004/?customer_id={runtime['customer_id']}", wait_until="domcontentloaded")
        status, body = ask(page, QUESTION)
        record("browser grounded answer", status == 200 and body.get("status") == "success"
               and all(word in body.get("answer", "").upper() for word in ["PENDING", "CONFIRMED", "CANCELLED"]), body)
        citations = body["citations"]
        record("citations point to real Orders docs", bool(citations) and all(
            c["source_id"].startswith("knowledge/student-4/") and (ROOT / "ai-services/rag-server" / c["source_id"]).is_file()
            for c in citations), citations)
        expect(page.locator("#ragResult")).to_have_attribute("data-state", "success")
        expect(page.locator("#ragConfidence")).to_have_text("Confidence: " + body["confidence_category"])
        expect(page.locator("#ragSources li")).to_have_count(len(citations))
        record("answer/source/confidence UI", page.locator("#ragAnswer").text_content() == body["answer"], body["confidence_category"])
        page.locator("section[aria-labelledby=ragHeading]").screenshot(path=str(RUN / "rag-success.png"))
        status, cancelled = ask(page, "Can a CONFIRMED order be cancelled?")
        record("cancellation answer", status == 200 and cancelled.get("status") == "success"
               and "CANCEL" in cancelled.get("answer", "").upper(), cancelled)
        status, body = ask(page, "What is the weather forecast in Sydney tomorrow?")
        record("insufficient context", status == 200 and body.get("status") == "insufficient_context"
               and body.get("citations") == [] and body.get("confidence_category") == "Insufficient", body)
        expect(page.locator("#ragStatus")).to_have_text("Not enough information")
        expect(page.locator("#ragSources")).to_have_text("Sources: none")
        page.locator("section[aria-labelledby=ragHeading]").screenshot(path=str(RUN / "rag-insufficient.png"))
        host = str(Path(__file__).with_name("host_servers.py"))
        subprocess.run([sys.executable, host, "rag", "stop"], check=True, capture_output=True)
        time.sleep(1)
        try:
            status, body = ask(page, QUESTION)
            record("RAG outage", status == 503 and body.get("status") == "error" and "answer" not in body, body)
            expect(page.locator("#ragStatus")).to_have_text("Orders guide unavailable")
            expect(page.locator("#ragConfidence")).to_be_empty()
            expect(page.locator("#ragSources")).to_be_empty()
            page.locator("section[aria-labelledby=ragHeading]").screenshot(path=str(RUN / "rag-outage.png"))
        finally:
            subprocess.run([sys.executable, host, "rag"], check=True, capture_output=True)
            for _ in range(60):
                try:
                    if requests.get(RAG + "/health", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.5)
        status, body = ask(page, QUESTION)
        record("RAG recovery", status == 200 and body.get("status") == "success", body)
        browser.close()
except Exception as exc:
    report.append({"check": "exception", "result": "FAIL", "detail": type(exc).__name__})
    (RUN / "rag-results.json").write_text(json.dumps(report, indent=2))
    print("FAIL", type(exc).__name__, flush=True)
raise SystemExit(result_exit_code(report))
