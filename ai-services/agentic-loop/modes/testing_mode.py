"""Review feature security scans and endpoint tests; default to Student 1."""
import os
import re
import subprocess
import sys
from pathlib import Path

from ollama_client import ask

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "testing_review_prompt.txt"
SCAN_PATHS = ["student-1", "ai-services", "scripts"]
POST_COMMIT_DIR = "student-1/tests/post_commit"
HOOKS = ["Ruff security scan", "detect-secrets scan", "pip-audit dependency scan"]


def _run(command, *, env=None):
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=900, env=env)  # noqa: S603
    return result.returncode, result.stdout + result.stderr


def run(stage, feature="student-1"):
    if feature not in {"student-1", "student-4"}:
        raise ValueError("Unsupported testing feature")
    orders = feature == "student-4"
    scan_paths = ["student-4", "shared", "ai-services", "scripts"] if orders else SCAN_PATHS
    post_commit_dir = "student-4/tests/post_commit" if orders else POST_COMMIT_DIR
    stage("PLAN", f"Pre-commit scans on {', '.join(scan_paths)}, then endpoint tests in {post_commit_dir}")
    if orders:
        stage("PLAN", "Local endpoint re-run; remote CI evidence must be linked separately")
    results = []

    def check(description, ok, detail):
        stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} - {description} -> {detail}")
        results.append((description, bool(ok), detail))

    listed_code, listed = _run(["git", "ls-files", "-z", *scan_paths])  # noqa: S607
    files = [name for name in listed.split("\0") if name]
    if listed_code != 0 or not files:
        stage("OBSERVE", "FAIL: cannot enumerate tracked scan files")
        return False
    stage("ACT", f"pre-commit run on {len(files)} tracked files")
    code, scan = _run([sys.executable, "-m", "pre_commit", "run", "--files", *files])

    for hook in HOOKS:
        line = next((line for line in scan.splitlines() if line.startswith(hook)), "")
        status = "Passed" if line.endswith("Passed") else "Skipped" if "Skipped" in line else "Failed"
        check(f"Pre-commit: {hook}", (status == "Passed" if orders else status in ("Passed", "Skipped")), status)
    check("Pre-commit: overall result", code == 0, f"exit code {code}")
    ignore_file = REPO_ROOT / "scripts" / "test" / "pip-audit-ignore.txt"
    ignored_ids = [line.split("#", 1)[0].strip() for line in ignore_file.read_text(encoding="utf-8").splitlines()]
    ignored_ids = [i for i in ignored_ids if i]
    stage("OBSERVE", f"Accepted pip-audit exceptions: {len(ignored_ids)} ({', '.join(ignored_ids)}), "
                     "documented with reasons in scripts/test/pip-audit-ignore.txt")

    stage("ACT", f"pytest {post_commit_dir}")
    test_env = dict(os.environ)
    if orders:
        test_env.update({key: "false" for key in
                         ("AI_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED")})
    code, tests = _run([sys.executable, "-m", "pytest", post_commit_dir, "-v"], env=test_env)
    passed = re.search(r"(\d+) passed", tests)
    failed = re.search(r"(\d+) failed", tests)
    passed_n = int(passed.group(1)) if passed else 0
    check("Post-commit: all endpoint tests pass", code == 0 and passed_n > 0,
          f"passed={passed_n} failed={failed.group(1) if failed else 0}")
    names = re.findall(r"::(test_\w+)", tests)
    endpoints = {"list_reviews": any("list_reviews" in n for n in names),
                 "get_review_stats": any("review_stats" in n for n in names)}
    if orders:
        expected = {
            "start_order_workflow": "test_start_order_workflow_requires_staff_and_forces_orders_evidence",
            "record_order_decision": "test_record_order_decision_binds_staff_identity_and_blocks_other_features",
        }
        endpoints = {endpoint: bool(re.search(r"::" + re.escape(test) + r"\s+PASSED\b", tests))
                     for endpoint, test in expected.items()}
    check("Post-commit: tests cover two endpoint functions", all(endpoints.values()), str(endpoints))

    passed_count = sum(1 for _, ok, _ in results if ok)
    evidence = "\n".join(f"{'PASS' if ok else 'FAIL'}: {d} ({detail})" for d, ok, detail in results)
    stage("ADAPT", "Asking Ollama to review the evidence (advisory only, pass/fail comes from the checks)")
    review, error = ask(PROMPT_FILE.read_text(encoding="utf-8").format(evidence=evidence))
    review_complete = not error and isinstance(review, str) and bool(review.strip())
    if not review_complete:
        stage("ADAPT", "Review incomplete: Ollama did not return a usable review")
    else:
        for line in review.splitlines():
            if line.strip():
                stage("REVIEW", line.strip())

    stage("ADAPT", f"{passed_count}/{len(results)} checks passed")
    if orders:
        stage("OBSERVE", f"AI review completion: {'PASS' if review_complete else 'FAIL'}")
    return passed_count == len(results) and (review_complete or not orders)
