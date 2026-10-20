import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import requests
from playwright.sync_api import sync_playwright, expect

from validation_checks import route_resource

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(os.environ["ORDERS_VALIDATION_RUN"]).resolve()
sys.path.insert(0, str(ROOT / "ai-services/agentic-loop"))
from modes.orders_mode import CASES

EXTRA = [
    ("delivery_paraphrase", "On which day should I expect my confirmed purchase to arrive?", "correct_abstention"),
    ("refund_paraphrase", "How long until the money for my cancelled purchase appears in my account?", "correct_abstention"),
    ("refund_implemented", "Is refund processing implemented by order cancellation?", "supported"),
    ("delivery_implemented", "Does CONFIRMED mean shipped or delivered?", "supported"),
    # Intentional Korean inputs exercise multilingual retrieval and abstention.
    ("refund_korean", "환불 기능이 구현되어 있나요?", "supported"),
    ("refund_delay_korean", "환불이 며칠 뒤 입금되나요?", "correct_abstention"),
]


def wait_http(url):
    for _ in range(80):
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(.5)
    raise RuntimeError("validation service did not start")


def main():
    parser = argparse.ArgumentParser(description="Capture real Orders UI answers; manual claim review required")
    parser.add_argument("--reuse", action="store_true", help="Reuse the existing isolated DB/index")
    parser.add_argument("--capture-name", default="first", choices=("first", "qwen05", "repaired", "assessed", "decision", "lines", "ranked", "final", "coverage"))
    parser.add_argument("--include-optional", action="store_true", help="Also capture optional multilingual diagnostics")
    args = parser.parse_args()
    os.umask(0o077)
    if RUN.is_relative_to(ROOT):
        raise SystemExit("Choose a private RUN outside the repository")
    if RUN.exists() and not (args.reuse and (RUN / "root-override.json").exists() and (RUN / "image-data").is_dir()):
        raise SystemExit("Existing RUN: explicitly reuse a recognized isolated capture; never overwrite evidence")
    for port in (3004, 5004, 6004, 8200):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} occupied; no process stopped")
    RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
    (RUN / "image-data").mkdir(exist_ok=True)
    capture = RUN / "captures" / args.capture_name
    capture.mkdir(parents=True, mode=0o700)  # Refuse a repeated evidence filename.
    # Root Compose is the base; override ONLY the three Orders feature services.
    # DB command never invokes init_db.py; fresh schema is CREATE/PRAGMA only.
    override = {"services": {
        "student4-database": {
            "image": "student4-orders:release1-local",
            "command": ["python", "/validation/image_check.py", "serve-db"],
            "volumes": [f"{ROOT}/scripts/orders/image_check.py:/validation/image_check.py:ro",
                        f"{RUN}/image-data:/validation-data"]},
        "student4-backend": {"image": "student4-orders:release1-local",
            "environment": {"AI_ENABLED": "false", "MCP_ENABLED": "false", "RAG_ENABLED": "true",
                            "ORDERS_MCP_SECRET": "", "RAG_URL": "http://host.docker.internal:8200"}},
        "student4-frontend": {"image": "student4-orders:release1-local"},
    }}
    config = RUN / "root-override.json"
    config.write_text(json.dumps(override, indent=2))
    prefix = ["docker", "compose", "-p", "orders-rag-followup", "-f", str(ROOT / "docker-compose.yml"), "-f", str(config)]
    env = dict(os.environ, OLLAMA_MODEL=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
               PORT="8200", ORDERS_RAG_MODEL=os.getenv("ORDERS_RAG_MODEL", "qwen2.5:3b"),
               ORDERS_RAG_CAPTURE="true", ORDERS_RAG_DOCUMENTS_ONLY="true",
               ORDERS_RAG_CAPTURE_DIR=str(capture),
               ANONYMIZED_TELEMETRY="False")
    evidence = {"feature": "student-4", "model": env["OLLAMA_MODEL"],
                "orders_model": env["ORDERS_RAG_MODEL"],
                "seed": 42, "temperature": 0, "num_predict": 128,
                "coverage_num_predict": 16, "model_budget_seconds": 90,
                "cases": [], "ui_checks": []}
    def save():
        (capture / "browser-evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    log = (capture / "rag-server.log").open("a")
    server = None
    try:
        subprocess.run(prefix + ["config", "--quiet"], check=True)
        subprocess.run(prefix + ["up", "-d", "--no-build", "--no-deps", "student4-database", "student4-backend", "student4-frontend"], check=True)
        server = subprocess.Popen([sys.executable, str(ROOT / "scripts/orders/serve_rag.py")], env=env, stdout=log, stderr=log)
        wait_http("http://localhost:8200/health")
        wait_http("http://localhost:5004/api/health")
        wait_http("http://localhost:3004/")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 1000})
            context.route("**/*", route_resource)
            page = context.new_page()
            page.goto("http://localhost:3004/", wait_until="domcontentloaded")
            def ask(query):
                page.locator("#ragQuery").fill(query)
                with page.expect_response(lambda r: "/api/rag/answer" in r.url, timeout=135000) as captured:
                    page.locator("#ragButton").click()
                expect(page.locator("#ragButton")).to_be_enabled(timeout=135000)
                return captured.value.status, captured.value.json()
            cases = CASES + [c for c in EXTRA if args.include_optional or not c[0].endswith("_korean")]
            for case_id, query, expected in cases:
                retrieval = requests.post("http://localhost:8200/retrieve", json={"query": query, "feature": "student-4", "k": 5}, timeout=130).json()
                started = time.monotonic()
                status, body = ask(query)
                elapsed = time.monotonic() - started
                ui = {key: page.locator(selector).inner_text() for key, selector in [
                    ("status", "#ragStatus"), ("answer", "#ragAnswer"), ("confidence", "#ragConfidence"), ("sources", "#ragSources")]}
                ui["data_state"] = page.locator("#ragResult").get_attribute("data-state")
                ok = (status == 200 and ui["answer"] == body.get("answer") and ui["data_state"] == body.get("status")
                      and ui["confidence"] == "Confidence: " + body.get("confidence_category", ""))
                if body.get("status") == "insufficient_context":
                    ok = ok and ui["status"] == "Not enough information" and ui["sources"] == "Sources: none" and body.get("citations") == [] and body.get("confidence_category") == "Insufficient"
                elif body.get("status") == "success":
                    ok = ok and bool(body.get("citations")) and all(c["source_id"] in ui["sources"] for c in body["citations"])
                evidence["cases"].append({"id": case_id, "query": query, "expected": expected, "required": not case_id.endswith("_korean"), "http": status,
                    "transport_ok": status == 200 and retrieval.get("status") == "success", "response": body,
                    "elapsed_seconds": round(elapsed, 3), "retrieval": retrieval, "ui": ui})
                evidence["ui_checks"].append({"id": case_id, "passed": bool(ok)})
                page.locator("section[aria-labelledby=ragHeading]").screenshot(path=str(capture / (case_id + ".png")))
                save()
                print(case_id, status, body.get("status"), "UI", ok, flush=True)
            # Existing Student 1 branch, same public-documents index; no Reviews DB.
            evidence["student1"] = []
            for query in ["When does a review get flagged?", "Can I review a product I did not buy?", "What is the weather in Sydney?"]:
                payload = {"query": query, "feature": "student-1", "k": 5}
                retrieval = requests.post("http://localhost:8200/retrieve", json=payload, timeout=130).json()
                response = requests.post("http://localhost:8200/answer", json=payload, timeout=130)
                evidence["student1"].append({"query": query, "http": response.status_code, "response": response.json(), "retrieval": retrieval})
                save()
            # Actual server outage, no browser mocks. Stop only our own child.
            server.terminate()
            server.wait(timeout=10)
            status, body = ask(CASES[0][1])
            ok = status == 503 and body.get("status") == "error" and "answer" not in body
            ok = ok and page.locator("#ragStatus").inner_text() == "Orders guide unavailable"
            ok = ok and not page.locator("#ragConfidence").inner_text() and not page.locator("#ragSources").inner_text()
            evidence["outage"] = {"http": status, "response": body, "ui_passed": ok}
            page.locator("section[aria-labelledby=ragHeading]").screenshot(path=str(capture / "outage.png"))
            save()
            browser.close()
        # Separate five-case file consumed by the existing shared analyst-review mode.
        (capture / "agentic-evidence.json").write_text(json.dumps({"cases": evidence["cases"][:5]}, indent=2, ensure_ascii=False) + "\n")
        print("REVIEW_REQUIRED: compare all answers and retrieved text; collection is not correctness PASS")
    except Exception as exc:
        evidence["collection_error"] = type(exc).__name__
        save()
        raise
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()  # Only the child process started by this invocation.
                server.wait(timeout=10)
        log.close()
        subprocess.run(prefix + ["stop", "student4-backend", "student4-frontend", "student4-database"], check=True)
        save()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
