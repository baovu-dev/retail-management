"""Testing Review: re-runs Student 1's pre-commit security scans and post-commit endpoint tests, then reviews the results."""
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


def _run(command):
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=900)  # noqa: S603
    return result.returncode, result.stdout + result.stderr


def run(stage):
    stage("PLAN", f"Pre-commit scans on {', '.join(SCAN_PATHS)}, then post-commit tests in {POST_COMMIT_DIR}")
    results = []

    def check(description, ok, detail):
        stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} - {description} -> {detail}")
        results.append((description, bool(ok), detail))

    _, listed = _run(["git", "ls-files", *SCAN_PATHS])  # noqa: S607
    files = listed.split()
    stage("ACT", f"pre-commit run on {len(files)} tracked files")
    code, scan = _run(["pre-commit", "run", "--files", *files])  # noqa: S607

    for hook in HOOKS:
        line = next((l for l in scan.splitlines() if l.startswith(hook)), "")
        status = "Passed" if line.endswith("Passed") else "Skipped" if "Skipped" in line else "Failed"
        check(f"Pre-commit: {hook}", status in ("Passed", "Skipped"), status)
    check("Pre-commit: overall result", code == 0, f"exit code {code}")
    ignore_file = REPO_ROOT / "scripts" / "test" / "pip-audit-ignore.txt"
    ignored_ids = [l.split("#", 1)[0].strip() for l in ignore_file.read_text(encoding="utf-8").splitlines()]
    ignored_ids = [i for i in ignored_ids if i]
    stage("OBSERVE", f"Accepted pip-audit exceptions: {len(ignored_ids)} ({', '.join(ignored_ids)}), "
                     "documented with reasons in scripts/test/pip-audit-ignore.txt")

    stage("ACT", f"pytest {POST_COMMIT_DIR}")
    code, tests = _run([sys.executable, "-m", "pytest", POST_COMMIT_DIR, "-v"])
    passed = re.search(r"(\d+) passed", tests)
    failed = re.search(r"(\d+) failed", tests)
    passed_n = int(passed.group(1)) if passed else 0
    check("Post-commit: all endpoint tests pass", code == 0 and passed_n > 0,
          f"passed={passed_n} failed={failed.group(1) if failed else 0}")
    names = re.findall(r"::(test_\w+)", tests)
    endpoints = {"list_reviews": any("list_reviews" in n for n in names),
                 "get_review_stats": any("review_stats" in n for n in names)}
    check("Post-commit: tests cover two endpoint functions", all(endpoints.values()), str(endpoints))

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

    stage("ADAPT", f"{passed_count}/{len(results)} checks passed")
    return passed_count == len(results)