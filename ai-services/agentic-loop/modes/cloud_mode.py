"""Cloud Deployment Review: checks the deployment report, re-checks the live app, then records the human release decision."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from ollama_client import ask

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "docs" / "release-2" / "evidence" / "cloud"
REPORT = EVIDENCE_DIR / "deployment-results.md"
DECISIONS = EVIDENCE_DIR / "release-decisions.jsonl"
PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "cloud_review_prompt.txt"
DECISION_OPTIONS = ["Approve", "Approve with notes", "Reject"]


def _ask_human_decision(stage):
    """The release decision must come from a person, so it is never automated."""
    if not sys.stdin.isatty():
        stage("ADAPT", "No terminal attached, so the release decision stays pending")
        return {"decision": "Pending", "reviewer": "", "reason": "No human reviewer present"}
    print("\nRelease decision options:")
    for number, option in enumerate(DECISION_OPTIONS, start=1):
        print(f"  {number} - {option}")
    choice = ""
    while choice not in {"1", "2", "3"}:
        choice = input("Choose 1-3: ").strip()
    reviewer = input("Your name: ").strip()
    reason = input("Reason for your decision: ").strip()
    return {"decision": DECISION_OPTIONS[int(choice) - 1], "reviewer": reviewer, "reason": reason}


def run(stage):
    stage("PLAN", "Check the deployment report, re-check the live app, then ask for the human release decision")
    results = []

    def check(description, ok, detail):
        stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} - {description} -> {detail}")
        results.append((description, bool(ok), detail))

    if not REPORT.exists():
        stage("ADAPT", f"FAIL: {REPORT.relative_to(REPO_ROOT)} not found. Run scripts/deploy/deployment-testing.sh first.")
        return False

    text = REPORT.read_text(encoding="utf-8")
    domain_match = re.search(r"Environment domain: (\S+)", text)
    domain = domain_match.group(1) if domain_match else ""
    stage("ACT", f"Reading {REPORT.relative_to(REPO_ROOT)} (domain {domain})")

    public_rows = [l for l in text.splitlines() if l.startswith("| ") and "https://" in l]
    check("Report: every public app responded", bool(public_rows) and all(l.rstrip().endswith("| PASS |") for l in public_rows),
          f"{sum(l.rstrip().endswith('| PASS |') for l in public_rows)}/{len(public_rows)} passed")
    baseline_rows = [l for l in text.splitlines() if "disabled" in l and l.startswith("| ")]
    check("Report: AI-Mode, MCP, RAG and Multi-Agent disabled", len(baseline_rows) == 4 and all(l.rstrip().endswith("| PASS |") for l in baseline_rows),
          f"{len(baseline_rows)} baseline rows")
    internal_rows = [l for l in text.splitlines() if re.match(r"\| \S+ \| (true|false) \|", l)]
    check("Report: databases and internal backends are internal-only", bool(internal_rows) and all("| false | PASS |" in l for l in internal_rows),
          f"{len(internal_rows)} internal apps")
    check("Report: overall result is PASS", "## Overall: PASS" in text, "Overall line")

    stage("ACT", "Re-checking the live Reviews app in Azure")
    try:
        stats = requests.get(f"https://student1-backend.{domain}/reviews/stats", timeout=90).json()
        check("Live: Reviews backend reads its internal database", "total_reviews" in stats, json.dumps(stats))
        code = requests.post(f"https://student1-backend.{domain}/mcp/rating-summary", data={"product_id": 101}, timeout=90).status_code
        check("Live: MCP is still disabled in the cloud", code == 403, f"HTTP {code}")
    except Exception as exc:
        check("Live: cloud app reachable", False, f"{exc.__class__.__name__}: {exc}")

    passed_count = sum(1 for _, ok, _ in results if ok)
    evidence = "\n".join(f"{'PASS' if ok else 'FAIL'}: {d} ({detail})" for d, ok, detail in results)
    stage("ADAPT", "Asking Ollama to review the evidence (advisory only, pass/fail comes from the checks)")
    review, error = ask(PROMPT_FILE.read_text(encoding="utf-8").format(evidence=evidence))
    if error:
        stage("ADAPT", f"Review skipped (Ollama error: {error})")
    else:
        for line in review.splitlines():
            if line.strip():
                stage("REVIEW", line.strip())

    stage("ADAPT", f"{passed_count}/{len(results)} checks passed. Human release decision required.")
    decision = _ask_human_decision(stage)
    decision["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decision["checks_passed"] = f"{passed_count}/{len(results)}"
    with DECISIONS.open("a", encoding="utf-8") as file:
        file.write(json.dumps(decision) + "\n")

    summary = (f"Human release decision: {decision['decision']} by {decision['reviewer'] or 'n/a'} "
               f"at {decision['timestamp']}; reason: {decision['reason'] or 'n/a'}")
    REPORT.write_text(re.sub(r"Human release decision: .*", summary, text), encoding="utf-8")
    stage("DECIDE", summary)

    released = decision["decision"] in ("Approve", "Approve with notes")
    return passed_count == len(results) and released