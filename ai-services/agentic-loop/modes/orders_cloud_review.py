"""Offline Orders cloud review of run-bound GitHub artifacts, never deployment."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from ollama_client import ask

ROOT = Path(__file__).resolve().parents[3]
LIMIT = 4 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
DECISIONS = {"Approve", "Approve with notes", "Reject"}
READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, BadZipFile)
REQUIRED_STEPS = {
    "Post-commit validation": {"Check required student endpoint coverage", "Run every student's post-commit endpoint tests"},
    "Deploy to Azure Container Apps": {"Deploy apps", "Validate deployment and generate evidence"},
}
ROUTES = {
    "frontend": ("GET", "/", 200),
    "health": ("GET", "/api/health", 200),
    "count": ("GET", "/api/orders/count", 200),
    "browser_api_access": ("GET", "/api/orders/count", 200),
    "create": ("POST", "/api/orders", 201),
    "read": ("GET", "/api/orders/{order_id}", 200),
    "update": ("PUT", "/api/orders/{order_id}", 200),
    "cancel": ("DELETE", "/api/orders/{order_id}", 200),
    "read_after_cancel": ("GET", "/api/orders/{order_id}", 200),
    "ai_disabled": ("POST", "/api/order-assistant", 403),
    "mcp_disabled": ("POST", "/api/mcp/order-status", 403),
    "rag_disabled": ("POST", "/api/rag/answer", 403),
    "multi_agent_disabled": ("POST", "/api/multi-agent/workflow", 403),
}
ASSERTIONS = {
    "frontend": {"orders_ui_rendered": True},
    "health": {"database_connected": True},
    "count": {},
    "browser_api_access": {"cors_allowed": True},
    "create": {"status": "PENDING"},
    "read": {"items_preserved": True},
    "update": {"status": "CONFIRMED"},
    "cancel": {"status": "CANCELLED"},
    "read_after_cancel": {"status": "CANCELLED", "items_preserved": True},
    **{key: {"code": "disabled"} for key in ROUTES if key.endswith("_disabled")},
}


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def object_json(raw):
    if len(raw) > LIMIT:
        raise ValueError("Evidence too large")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    result = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise ValueError("Evidence must be an object")
    return result


def artifact(reference, base, run_id, commit, expected_name):
    """Match the downloaded ZIP bytes to GitHub's artifact digest and run metadata."""
    metadata = object_json((base / reference["metadata_file"]).read_bytes())
    archive = base / reference["archive_file"]
    if archive.stat().st_size > LIMIT * 8:
        raise ValueError("Artifact too large")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    origin = metadata.get("workflow_run", {})
    if (metadata.get("name") != expected_name or metadata.get("expired") is not False
            or origin.get("id") != run_id or origin.get("head_sha") != commit
            or metadata.get("digest") != "sha256:" + digest):
        raise ValueError("Artifact provenance mismatch")
    with ZipFile(archive) as zipped:
        infos = zipped.infolist()
        if (len(infos) > 100 or sum(entry.file_size for entry in infos) > LIMIT * 8
                or len({entry.filename for entry in infos}) != len(infos)
                or any(entry.file_size > LIMIT for entry in infos)):
            raise ValueError("Ambiguous or oversized artifact")
        # No extraction and no execution of archived files.
        files = {entry.filename: zipped.read(entry) for entry in infos if not entry.is_dir()}
    return files, digest


def origin(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        return None
    return value.rstrip("/")


def junit_passes(raw, student):
    # Reject DTD/entities before parsing bounded, digest-verified CI output.
    if (len(raw) > LIMIT or b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper()):
        return False
    tree = ET.fromstring(raw)  # noqa: S314 - bounded XML with DTD/entities rejected above
    cases = tree.findall(".//testcase")
    names = {case.get("name") for case in cases}
    suites = list(tree.iter("testsuite"))
    if any(int(suite.get(key, "0")) != 0 for suite in suites for key in ("errors", "failures", "skipped")):
        return False
    if (len(cases) < 2 or len(names) < 2 or None in names
            or any(case.find(tag) is not None for case in cases for tag in ("skipped", "failure", "error"))):
        return False
    if student == 4:
        return {"test_start_order_workflow_requires_staff_and_forces_orders_evidence",
                "test_record_order_decision_binds_staff_identity_and_blocks_other_features"} <= names
    return True


def routing_matches(report):
    """Check the saved public path against the current repository, not guessed DNS."""
    route = report.get("access", {})
    frontend, api = origin(route.get("frontend_origin")), origin(route.get("api_origin"))
    domain = route.get("environment_domain", "")
    domain_valid = isinstance(domain, str) and re.fullmatch(r"[a-z0-9.-]+\.azurecontainerapps\.io", domain) is not None
    apps = (ROOT / "scripts/deploy/apps.conf").read_text(encoding="utf-8")
    config = (ROOT / "scripts/deploy/render_app_spec.py").read_text(encoding="utf-8")
    frontend_code = (ROOT / "student-4/frontend/app.py").read_text(encoding="utf-8")
    # This checkout implements browser -> external API_BASE, without an API proxy.
    return (frontend is not None and api is not None and frontend != api
            and domain_valid and frontend == f"https://student4-frontend.{domain}"
            and api == f"https://student4-backend.{domain}"
            and route.get("kind") == "direct-public-backend"
            and any(line.startswith("student4-backend|student-4|5004|external|") for line in apps.splitlines())
            and '"API_BASE": url("student4-backend")' in config
            and '@app.route("/api/' not in frontend_code
            and route.get("frontend_app") == "student4-frontend"
            and route.get("api_app") == "student4-backend")


def behavior_checks(report):
    access = report.get("access", {})
    frontend, api = origin(access.get("frontend_origin")), origin(access.get("api_origin"))
    checks = report.get("checks", {})
    test_order = report.get("test_order_id")
    if not isinstance(checks, dict) or type(test_order) is not int or test_order <= 0:
        return False
    if "collector" in report:
        if report["collector"] != "orders-cloud-http-v1" or report.get("collection_status") != "complete":
            return False
        # A collector failure or unverified ownership must never be hidden by the older core schema.
        for name, method, path, statuses in (
                ("unauthenticated_create_denied", "POST", "/api/orders", {401, 403}),
                ("invalid_credential_denied", "POST", "/api/orders", {401, 403}),
                ("ownership_denied", "GET", f"/api/orders/{test_order}", {403})):
            row = checks.get(name, {})
            if (not isinstance(row, dict) or row.get("method") != method or not api
                    or row.get("url") != api + path or row.get("http_status") not in statuses
                    or row.get("passed") is not True or row.get("observed", {}).get("access_denied") is not True
                    or timestamp(row.get("timestamp")) is None):
                return False
    times = []
    for name, (method, path, status) in ROUTES.items():
        row = checks.get(name, {})
        if not isinstance(row, dict):
            return False
        expected_url = (frontend if name == "frontend" else api)
        if not expected_url:
            return False
        expected_url += path.replace("{order_id}", str(test_order))
        observed = row.get("observed", {})
        if not isinstance(observed, dict):
            return False
        if (row.get("method") != method or row.get("url") != expected_url
                or type(row.get("http_status")) is not int or row["http_status"] != status
                or row.get("passed") is not True
                or any(type(observed.get(key)) is not type(value) or observed[key] != value
                       for key, value in ASSERTIONS[name].items())):
            return False
        if name == "frontend" and observed.get("api_base") != api:
            return False
        if name == "browser_api_access" and row.get("request_origin") != frontend:
            return False
        if name in {"count", "browser_api_access"} and (type(observed.get("count")) is not int or observed["count"] < 0):
            return False
        if (name in {"create", "read", "update", "cancel", "read_after_cancel"}
                and (type(observed.get("order_id")) is not int or observed["order_id"] != test_order)):
            return False
        when = timestamp(row.get("timestamp"))
        if when is None:
            return False
        times.append(when)
    return times == sorted(times)


def evaluate(bundle, base):
    """Return only allowlisted facts; raw logs, bodies and arbitrary text stay private."""
    checks, identities = [], {}
    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
    run = object_json((base / bundle["run_file"]).read_bytes())
    run_id, commit = run.get("databaseId"), run.get("headSha")
    check("run_identity", type(run_id) is int and run_id > 0 and isinstance(commit, str) and SHA.fullmatch(commit) is not None)
    if not checks[-1]["passed"]:
        return checks, identities
    # The declared expected SHA prevents mixing different release candidates.
    check("expected_commit", bundle.get("expected_commit") == commit)
    started, ended = timestamp(run.get("createdAt")), timestamp(run.get("updatedAt"))
    check("run_provenance", run.get("url") == f"https://github.com/baovu-dev/retail-management/actions/runs/{run_id}"
          and started is not None and ended is not None and started <= ended <= datetime.now(timezone.utc))
    check("run_completed", run.get("status") == "completed" and run.get("conclusion") == "success")
    jobs = run.get("jobs", [])
    for job_name, steps in REQUIRED_STEPS.items():
        matching = [job for job in jobs if isinstance(job, dict) and job.get("name") == job_name] if isinstance(jobs, list) else []
        ok = len(matching) == 1 and matching[0].get("status") == "completed" and matching[0].get("conclusion") == "success"
        for step in steps:
            found = [item for item in matching[0].get("steps", []) if isinstance(item, dict) and item.get("name") == step] if matching else []
            ok = ok and len(found) == 1 and found[0].get("status") == "completed" and found[0].get("conclusion") == "success"
        check("validation_job" if job_name == "Post-commit validation" else "deployment_job", ok)
    identities["repository_configuration"] = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in ("scripts/deploy/apps.conf", "scripts/deploy/render_app_spec.py",
                         "student-4/frontend/app.py", "student-4/frontend/templates/index.html",
                         ".github/workflows/cloud-deployment.yml")
    }
    identities.update(run_id=run_id, commit_sha=commit,
                      run_export_sha256=hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest())
    for key, name in (("validation", "cloud-validation-tests"), ("deployment", "cloud-deployment-evidence")):
        try:
            files, digest = artifact(bundle[key], base, run_id, commit, name)
            identities[key + "_artifact_sha256"] = digest
            check(key + "_artifact_provenance", True)
            if key == "validation":
                scope = files.get("scope.txt", b"").decode("utf-8")
                check("validation_scope", f"Commit: {commit}" in scope.splitlines())
                coverage = files.get("coverage.log", b"").decode("utf-8")
                check("team_coverage", "FAIL:" not in coverage and all(
                    f"PRESENT: student-{student} endpoint test files (execution still required)" in coverage.splitlines()
                    for student in range(1, 6)))
                ready = files.get("readiness.log", b"").decode("utf-8").splitlines()
                workflow = (ROOT / ".github/workflows/cloud-deployment.yml").read_text(encoding="utf-8")
                urls = re.search(r"for url in ([^\n;]+); do", workflow)
                expected = {"PASS: " + url for url in urls[1].split()} if urls else set()
                check("readiness", bool(expected) and set(ready) == expected)
                for student in range(1, 6):
                    raw = files.get(f"student-{student}.xml", b"")
                    try:
                        passed = bool(raw) and junit_passes(raw, student)
                    except ET.ParseError:
                        passed = False
                    check(f"student_{student}_executed_tests", passed)
            else:
                raw = files.get("orders-cloud-evidence.json")
                check("orders_deployment_evidence_present", raw is not None)
                if raw is None:
                    continue
                report = object_json(raw)
                recorded = timestamp(report.get("timestamp"))
                check("deployment_identity", report.get("feature") == "student-4"
                      and report.get("run_id") == run_id and report.get("commit_sha") == commit
                      and recorded is not None and started is not None and ended is not None
                      and started <= recorded <= ended)
                identities["deployment_timestamp"] = recorded.isoformat() if recorded else None
                check("mandatory_profile", report.get("profile") == "mandatory-ai-disabled")
                check("public_access_matches_repository", routing_matches(report))
                check("orders_public_behavior", behavior_checks(report))
                rows = report.get("checks", {})
                check("behavior_run_window", isinstance(rows, dict) and bool(rows)
                      and started is not None and recorded is not None
                      and all(isinstance(row, dict) and timestamp(row.get("timestamp")) is not None
                              and started <= timestamp(row["timestamp"]) <= recorded for row in rows.values()))
        except READ_ERRORS:
            check(key + "_artifact_readable", False)
    return checks, identities


def human_decision(path, identity, deployed_at):
    if path is None:
        return {"decision": "Pending"}, False
    record = object_json(Path(path).read_bytes())
    # This is a person's supplied decision, not something inferred from model prose.
    reviewer, reason = record.get("reviewer"), record.get("reason")
    when = timestamp(record.get("timestamp"))
    valid = (record.get("decision") in DECISIONS and record.get("evidence_identity") == identity
             and isinstance(reviewer, str) and 0 < len(reviewer.strip()) <= 100
             and isinstance(reason, str) and 0 < len(reason.strip()) <= 1000
             and not sensitive_text(reviewer + " " + reason)
             and when is not None and deployed_at is not None
             and deployed_at <= when <= datetime.now(timezone.utc))
    if not valid:
        return {"decision": "Pending"}, False
    # Do not pass human text to Ollama or terminal logs.
    return {key: record[key] for key in ("decision", "reviewer", "reason", "timestamp", "evidence_identity")}, True


def sensitive_text(value):
    return re.search(r"(?i)(bearer\s+\S+|(?:password|secret|token|authorization)\s*[:=]\s*\S+|eyJ[\w-]+\.[\w-]+\.[\w-]+|gh[pousr]_[\w]+)", value) is not None


def advisory_result(text, checks):
    """Only a bounded vocabulary can leave the model boundary, never free text."""
    result = object_json(text.encode())
    summary = result.get("summary")
    findings = result.get("findings")
    recommendations = result.get("recommendations")
    names = {check["name"] for check in checks}
    allowed = {"collect_missing_evidence", "resolve_failed_checks", "verify_public_path",
               "record_human_decision", "review_bonus_separately"}
    if (summary not in {"incomplete", "ready_for_human_review"} or not isinstance(findings, list)
            or not isinstance(recommendations, list) or not findings or len(findings) != len(checks)
            or len(recommendations) > len(allowed)
            or any(not isinstance(item, str) or item not in allowed for item in recommendations)
            or any(not isinstance(item, dict) or item.get("check") not in names
                   or item.get("assessment") not in {"passed", "failed", "unverified"} for item in findings)):
        raise ValueError("Unsupported advisory format")
    finding_names = [item["check"] for item in findings]
    if len(set(finding_names)) != len(finding_names) or set(finding_names) != names:
        raise ValueError("Advisory findings must cover every check exactly once")
    return {"summary": summary,
            "findings": [{"check": item["check"], "assessment": item["assessment"]} for item in findings],
            "recommendations": recommendations}


def run(stage, args):
    checks, identities = [], {}
    bundle_path = getattr(args, "evidence_file", None)
    bundle_digest = None
    try:
        raw = Path(bundle_path).read_bytes() if bundle_path else b""
        bundle_digest = hashlib.sha256(raw).hexdigest() if raw else None
        bundle = object_json(raw)
        checks, identities = evaluate(bundle, Path(bundle_path).resolve().parent)
    except READ_ERRORS:
        checks.append({"name": "evidence_bundle_readable", "passed": False})
    identities["bundle_sha256"] = bundle_digest
    identity = hashlib.sha256(json.dumps({"sources": identities, "checks": checks}, sort_keys=True).encode()).hexdigest()
    for check in checks:
        stage("OBSERVE", f"{'PASS' if check['passed'] else 'FAIL'} - {check['name']}")
    complete = bool(checks) and all(check["passed"] for check in checks)
    decision, decision_valid = {"decision": "Pending"}, False
    try:
        decision, decision_valid = human_decision(getattr(args, "cloud_decision_file", None), identity,
                                                 timestamp(identities.get("deployment_timestamp")))
    except READ_ERRORS:
        pass
    review, error = None, None
    advisory = None
    if not getattr(args, "cloud_no_advisory", False):
        # A fixed vocabulary of deterministic facts prevents leaking raw artifact data.
        evidence = json.dumps({"feature": "student-4", "profile": "mandatory-ai-disabled",
                               "checks": checks, "bonus": "unverified", "human_release": "separate decision required"})
        prompt = (Path(__file__).resolve().parents[1] / "prompts/orders_cloud_review_prompt.txt").read_text(encoding="utf-8")
        try:
            review, error = ask(prompt.format(evidence=evidence), timeout=90)
        except Exception:
            error = "advisory_unavailable"
        if not error and isinstance(review, str) and review.strip():
            try:
                advisory = advisory_result(review, checks)
            except READ_ERRORS:
                pass
    reviewed = advisory is not None
    accepted = decision_valid and decision["decision"] in {"Approve", "Approve with notes"}
    release = "approved" if complete and reviewed and accepted else "pending"
    if decision_valid and decision["decision"] == "Reject":
        release = "rejected"
    packet = {
        "feature": "student-4", "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_identity": identity, "sources": identities, "checks": checks,
        "deterministic_passed": complete, "advisory_completed": reviewed,
        "advisory_review": advisory,
        "advisory_status": "completed; human assessment required" if reviewed else "not completed",
        "human_decision": decision, "human_decision_valid": decision_valid,
        "release_status": release, "bonus_claims": "unverified; not assessed by this mandatory-profile review",
        "limitations": ["Offline artifact review; no current live Azure requests.",
                        "Artifact checks establish consistency, not independent attestation of a human-authored report.",
                        "JUnit execution alone does not establish two distinct endpoint functions for teammates; owners must document mapping.",
                        "Database persistence and all other team features require separate release evidence."],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / f"student-4-cloud-review-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}.json"
    with target.open("x", encoding="utf-8") as output:
        json.dump(packet, output, indent=2, ensure_ascii=False)
        output.write("\n")
    stage("OBSERVE", f"Deterministic evidence: {'PASS' if complete else 'INCOMPLETE/FAILED'}")
    stage("OBSERVE", f"Ollama advisory: {'completed' if reviewed else 'not completed'}; cannot override checks")
    stage("DECIDE", f"Release: {release}; separate human decision required")
    stage("OBSERVE", "Separate Orders cloud review packet written")
    return release == "approved"
