"""Synthetic, offline fixtures exercise release gates; these are not cloud evidence."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import secrets
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def complete_advisory(prompt, **kwargs):
    checks = json.loads(prompt.split("\nEvidence:\n", 1)[1])["checks"]
    # A complete positive advisory still cannot override deterministic failures.
    return json.dumps({"summary": "ready_for_human_review",
                       "findings": [{"check": check["name"], "assessment": "passed"} for check in checks],
                       "recommendations": ["record_human_decision"]}), None


@pytest.fixture
def review():
    fake = ModuleType("ollama_client")
    fake.ask = Mock(side_effect=complete_advisory)
    spec = importlib.util.spec_from_file_location("orders_cloud_fixture", ROOT / "ai-services/agentic-loop/modes/orders_cloud_review.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"ollama_client": fake}):
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def evidence(tmp_path, review):
    # All success data is confined to this temporary test fixture.
    commit = "a" * 40
    run_id = 42
    run = {"databaseId": run_id, "headSha": commit, "status": "completed", "conclusion": "success",
           "url": "https://github.com/baovu-dev/retail-management/actions/runs/42",
           "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:10:00Z",
           "jobs": [{"name": name, "status": "completed", "conclusion": "success",
                     "steps": [{"name": step, "status": "completed", "conclusion": "success"} for step in steps]}
                    for name, steps in review.REQUIRED_STEPS.items()]}
    (tmp_path / "run.json").write_text(json.dumps(run))
    workflow = (ROOT / ".github/workflows/cloud-deployment.yml").read_text()
    urls = review.re.search(r"for url in ([^\n;]+); do", workflow)[1].split()
    validation = {"scope.txt": f"Commit: {commit}\n", "readiness.log": "\n".join("PASS: " + url for url in urls),
                  "coverage.log": "\n".join(f"PRESENT: student-{n} endpoint test files (execution still required)" for n in range(1, 6))}
    for student in range(1, 6):
        names = ["test_first_endpoint", "test_second_endpoint"]
        if student == 4:
            names = ["test_start_order_workflow_requires_staff_and_forces_orders_evidence",
                     "test_record_order_decision_binds_staff_identity_and_blocks_other_features"]
        validation[f"student-{student}.xml"] = '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0">' + ''.join(
            f'<testcase name="{name}"/>' for name in names) + '</testsuite></testsuites>'
    domain = "fixture.australiaeast.azurecontainerapps.io"
    front = f"https://student4-frontend.{domain}"
    api = f"https://student4-backend.{domain}"
    deployment = {"feature": "student-4", "run_id": run_id, "commit_sha": commit,
                  "timestamp": "2026-01-01T00:09:00Z", "profile": "mandatory-ai-disabled", "test_order_id": 77,
                  "access": {"kind": "direct-public-backend", "frontend_origin": front, "api_origin": api,
                             "frontend_app": "student4-frontend", "api_app": "student4-backend", "environment_domain": domain}, "checks": {}}
    for name, (method, path, status) in review.ROUTES.items():
        observed = dict(review.ASSERTIONS[name])
        if name == "frontend":
            observed["api_base"] = api
        if name in {"count", "browser_api_access"}:
            observed["count"] = 0
        if name in {"create", "read", "update", "cancel", "read_after_cancel"}:
            observed["order_id"] = 77
        deployment["checks"][name] = {"method": method, "url": (front if name == "frontend" else api) + path.replace("{order_id}", "77"),
                                      "http_status": status, "passed": True, "observed": observed,
                                      "timestamp": "2026-01-01T00:05:00Z", "request_origin": front}
    bundle = {"expected_commit": commit, "run_file": "run.json",
              "validation": {"metadata_file": "validation-meta.json", "archive_file": "validation.zip"},
              "deployment": {"metadata_file": "deployment-meta.json", "archive_file": "deployment.zip"}}

    def write_artifacts():
        for key, files in (("validation", validation), ("deployment", {"orders-cloud-evidence.json": json.dumps(deployment)})):
            with ZipFile(tmp_path / f"{key}.zip", "w") as archive:
                for name, value in files.items():
                    archive.writestr(name, value)
            digest = hashlib.sha256((tmp_path / f"{key}.zip").read_bytes()).hexdigest()
            metadata = {"name": "cloud-validation-tests" if key == "validation" else "cloud-deployment-evidence",
                        "expired": False, "digest": "sha256:" + digest,
                        "workflow_run": {"id": run_id, "head_sha": commit}}
            (tmp_path / f"{key}-meta.json").write_text(json.dumps(metadata))
        (tmp_path / "bundle.json").write_text(json.dumps(bundle))
    write_artifacts()
    return SimpleNamespace(root=tmp_path, run=run, bundle=bundle, validation=validation, deployment=deployment, write=write_artifacts)


def execute(review, evidence, **kwargs):
    args = SimpleNamespace(evidence_file=evidence.root / "bundle.json", output_dir=evidence.root / "out",
                           cloud_decision_file=kwargs.get("decision"), cloud_no_advisory=kwargs.get("no_advisory", False))
    logs = []
    result = review.run(lambda *line: logs.append(line), args)
    packet = json.loads(sorted(args.output_dir.glob("*.json"))[-1].read_text())
    return result, packet, logs


def write_run(evidence):
    (evidence.root / "run.json").write_text(json.dumps(evidence.run))


def test_valid_evidence_does_not_automatically_approve(review, evidence):
    originals = {p.name: p.read_bytes() for p in evidence.root.iterdir() if p.is_file()}
    result, packet, _ = execute(review, evidence)
    assert not result
    assert packet["deterministic_passed"]
    assert packet["advisory_completed"]
    assert packet["release_status"] == "pending"
    assert packet["human_decision"] == {"decision": "Pending"}
    assert all((evidence.root / name).read_bytes() == raw for name, raw in originals.items())


@pytest.mark.parametrize("filename", ["bundle.json", "run.json", "validation.zip", "deployment.zip"])
def test_missing_evidence_cannot_pass(review, evidence, filename):
    (evidence.root / filename).unlink()
    result, packet, _ = execute(review, evidence)
    assert not result and not packet["deterministic_passed"]
    assert packet["release_status"] == "pending"


@pytest.mark.parametrize("job,conclusion", [(0, "failure"), (1, "skipped")])
def test_failed_validation_or_skipped_deployment_blocks_release(review, evidence, job, conclusion):
    evidence.run["jobs"][job]["conclusion"] = conclusion
    write_run(evidence)
    assert not execute(review, evidence)[1]["deterministic_passed"]


@pytest.mark.parametrize("student", [2, 3])
@pytest.mark.parametrize("problem", ["missing", "skipped", "failure"])
def test_required_teammate_execution_cannot_be_skipped(review, evidence, student, problem):
    key = f"student-{student}.xml"
    if problem == "missing":
        evidence.validation.pop(key)
    else:
        evidence.validation[key] = evidence.validation[key].replace('<testcase name="test_first_endpoint"/>',
            f'<testcase name="test_first_endpoint"><{problem}/></testcase>')
    evidence.write()
    assert not execute(review, evidence)[1]["deterministic_passed"]


@pytest.mark.parametrize("change", ["sha", "run", "digest", "coverage", "readiness", "legacy_report"])
def test_mismatched_or_insufficient_artifacts_fail(review, evidence, change):
    if change == "sha":
        evidence.bundle["expected_commit"] = "b" * 40
        evidence.write()
    elif change in {"run", "digest"}:
        path = evidence.root / "deployment-meta.json"
        meta = json.loads(path.read_text())
        if change == "run":
            meta["workflow_run"]["id"] = 43
        else:
            meta["digest"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(meta))
    elif change == "legacy_report":
        # The real existing markdown report does not establish Orders behavior.
        with ZipFile(evidence.root / "deployment.zip", "w") as zipped:
            zipped.writestr("deployment-results.md", (ROOT / "docs/release-2/evidence/cloud/deployment-results.md").read_bytes())
        meta_path = evidence.root / "deployment-meta.json"
        meta = json.loads(meta_path.read_text())
        meta["digest"] = "sha256:" + hashlib.sha256((evidence.root / "deployment.zip").read_bytes()).hexdigest()
        meta_path.write_text(json.dumps(meta))
    else:
        evidence.validation["coverage.log" if change == "coverage" else "readiness.log"] += "\nFAIL: required check"
        evidence.write()
    assert not execute(review, evidence)[1]["deterministic_passed"]


@pytest.mark.parametrize("change", ["unrelated_url", "internal_backend", "proxy", "wrong_order", "root_404", "bonus_profile", "wrong_time", "no_cors", "flag_only"])
def test_no_false_orders_cloud_success(review, evidence, change):
    report = evidence.deployment
    if change == "unrelated_url":
        report["checks"]["health"]["url"] = "https://unrelated.example/api/health"
    elif change == "internal_backend":
        report["access"]["api_origin"] = "http://student4-backend:5004"
    elif change == "proxy":
        report["access"]["kind"] = "frontend-proxy"
    elif change == "wrong_order":
        report["checks"]["read"]["observed"]["order_id"] = 78
    elif change == "root_404":
        report["checks"]["health"].update(url=report["access"]["api_origin"] + "/", http_status=404)
    elif change == "bonus_profile":
        report["profile"] = "ai-enabled"
    elif change == "wrong_time":
        report["timestamp"] = "2025-12-31T00:00:00Z"
    elif change == "no_cors":
        report["checks"]["browser_api_access"]["observed"]["cors_allowed"] = False
    else:
        report["checks"]["ai_disabled"]["observed"] = {"AI_ENABLED": False}
    evidence.write()
    result, packet, _ = execute(review, evidence)
    assert not result and not packet["deterministic_passed"]
    assert packet["bonus_claims"].startswith("unverified")


def test_separate_human_decision_binds_exact_evidence(review, evidence):
    _, pending, _ = execute(review, evidence)
    decision = {"decision": "Approve", "reviewer": "Synthetic test reviewer", "reason": "Synthetic fixture checks assessed.",
                "timestamp": datetime.now(timezone.utc).isoformat(), "evidence_identity": pending["evidence_identity"]}
    path = evidence.root / "decision.json"
    path.write_text(json.dumps(decision))
    result, packet, _ = execute(review, evidence, decision=path)
    assert result and packet["release_status"] == "approved"
    assert packet["human_decision"] == decision
    decision["evidence_identity"] = "0" * 64
    path.write_text(json.dumps(decision))
    assert execute(review, evidence, decision=path)[1]["release_status"] == "pending"


def test_rejection_and_model_failure_cannot_approve(review, evidence):
    _, pending, _ = execute(review, evidence)
    path = evidence.root / "decision.json"
    path.write_text(json.dumps({"decision": "Reject", "reviewer": "Synthetic reviewer", "reason": "Fixture rejection.",
                               "timestamp": datetime.now(timezone.utc).isoformat(), "evidence_identity": pending["evidence_identity"]}))
    assert execute(review, evidence, decision=path)[1]["release_status"] == "rejected"
    review.ask.side_effect = None
    review.ask.return_value = (None, "Bearer private-exception-text")
    result, packet, logs = execute(review, evidence)
    assert not result and not packet["advisory_completed"]
    assert "private-exception-text" not in json.dumps([packet, logs])


def test_customer_records_and_secret_text_never_reach_prompt_or_packet(review, evidence):
    secret_text = secrets.token_hex(20)
    evidence.deployment["customer_records"] = [{"email": "customer@example.test", "token": secret_text}]
    evidence.deployment["original_worker"] = "Original unsupported answer"
    evidence.deployment["corrected_output"] = "Human correction"
    evidence.write()
    _, packet, logs = execute(review, evidence)
    prompt = review.ask.call_args.args[0]
    assert secret_text not in prompt + json.dumps([packet, logs])
    assert "customer@example.test" not in prompt
    assert "Human correction" not in prompt
    response = json.loads(complete_advisory(prompt)[0])
    response["secret"] = secret_text
    review.ask.side_effect = None
    review.ask.return_value = (json.dumps(response), None)
    _, packet, logs = execute(review, evidence)
    assert secret_text not in json.dumps([packet, logs])


@pytest.mark.parametrize("raw", [b"not a zip", b"{}"])
def test_malformed_artifact_writes_failed_packet(review, evidence, raw):
    path = evidence.root / "validation.zip"
    path.write_bytes(raw)
    meta_path = evidence.root / "validation-meta.json"
    meta = json.loads(meta_path.read_text())
    meta["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    meta_path.write_text(json.dumps(meta))
    assert not execute(review, evidence)[1]["deterministic_passed"]


def test_no_advisory_mode_never_calls_model_or_approves(review, evidence):
    result, packet, _ = execute(review, evidence, no_advisory=True)
    review.ask.assert_not_called()
    assert not result and not packet["advisory_completed"]


def test_xml_entities_and_duplicate_json_are_rejected(review):
    assert not review.junit_passes(b'<!DOCTYPE x [<!ENTITY y "bad">]><testsuites/>', 2)
    with pytest.raises(ValueError):
        review.object_json(b'{"run_file":"first", "run_file":"second"}')


@pytest.mark.parametrize("field,value", [("reason", ""), ("reviewer", ""), ("timestamp", "2099-01-01T00:00:00Z"),
                                         ("reason", "Authorization=Bearer test-only-private-value")])
def test_incomplete_or_sensitive_human_decision_is_not_preserved(review, evidence, field, value):
    _, pending, _ = execute(review, evidence)
    record = {"decision": "Approve", "reviewer": "Synthetic reviewer", "reason": "Assessed synthetic fixture.",
              "timestamp": datetime.now(timezone.utc).isoformat(), "evidence_identity": pending["evidence_identity"]}
    record[field] = value
    path = evidence.root / "decision.json"
    path.write_text(json.dumps(record))
    result, packet, logs = execute(review, evidence, decision=path)
    assert not result and not packet["human_decision_valid"]
    assert packet["human_decision"] == {"decision": "Pending"}
    assert "test-only-private-value" not in json.dumps([packet, logs])


def test_explicit_approval_and_positive_advisory_cannot_override_failed_checks(review, evidence):
    evidence.run["jobs"][0]["conclusion"] = "failure"
    write_run(evidence)
    _, pending, _ = execute(review, evidence)
    record = {"decision": "Approve", "reviewer": "Synthetic reviewer", "reason": "Deliberately insufficient approval fixture.",
              "timestamp": datetime.now(timezone.utc).isoformat(), "evidence_identity": pending["evidence_identity"]}
    path = evidence.root / "decision.json"
    path.write_text(json.dumps(record))
    result, packet, _ = execute(review, evidence, decision=path)
    assert packet["human_decision_valid"] and packet["advisory_completed"]
    assert not result and packet["release_status"] == "pending"


def test_cli_preserves_student1_cloud_and_connects_orders(tmp_path, monkeypatch):
    loop = ROOT / "ai-services/agentic-loop"
    monkeypatch.syspath_prepend(str(loop))
    spec = importlib.util.spec_from_file_location("orders_cloud_cli_fixture", loop / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = Mock(return_value=True)
    monkeypatch.setitem(module.MODES, "cloud", old)
    monkeypatch.setattr(sys, "argv", ["main.py", "--mode", "cloud", "--output-dir", str(tmp_path / "old")])
    assert module.main() == 0
    old.assert_called_once()
    assert len(old.call_args.args) == 1
    from modes import orders_cloud_review
    connected = Mock(return_value=False)
    monkeypatch.setattr(orders_cloud_review, "run", connected)
    monkeypatch.setattr(sys, "argv", ["main.py", "--mode", "cloud", "--feature", "student-4",
                                     "--cloud-no-advisory", "--output-dir", str(tmp_path / "orders")])
    assert module.main() == 1
    connected.assert_called_once()
    assert connected.call_args.args[1].cloud_no_advisory
    assert old.call_count == 1


@pytest.mark.parametrize("problem", ["empty", "missing_field", "omitted_check", "duplicate_short", "duplicate_full", "unknown"])
def test_incomplete_findings_block_release_even_with_human_approval(review, evidence, problem):
    _, pending, _ = execute(review, evidence)
    path = evidence.root / "decision.json"
    path.write_text(json.dumps({"decision": "Approve", "reviewer": "Synthetic reviewer", "reason": "Assessed synthetic evidence.",
                               "timestamp": datetime.now(timezone.utc).isoformat(), "evidence_identity": pending["evidence_identity"]}))
    response = json.loads(complete_advisory(review.ask.call_args.args[0])[0])
    if problem == "empty":
        response["findings"] = []
    elif problem == "missing_field":
        response.pop("findings")
    elif problem == "omitted_check":
        response["findings"].pop()
    elif problem == "duplicate_short":
        response["findings"] = [response["findings"][0], response["findings"][0]]
    elif problem == "duplicate_full":
        response["findings"][-1] = dict(response["findings"][0])
    else:
        response["findings"][0]["check"] = "unknown_check"
    review.ask.side_effect = None
    review.ask.return_value = (json.dumps(response), None)
    result, packet, _ = execute(review, evidence, decision=path)
    assert packet["deterministic_passed"] and packet["human_decision_valid"]
    assert not packet["advisory_completed"]
    assert packet["advisory_review"] is None
    assert not result and packet["release_status"] == "pending"


def test_complete_disagreeing_findings_are_advisory_not_an_automatic_rejection(review, evidence):
    _, pending, _ = execute(review, evidence)
    path = evidence.root / "decision.json"
    path.write_text(json.dumps({"decision": "Approve", "reviewer": "Synthetic reviewer", "reason": "Human accepts evidence despite advisory disagreement.",
                               "timestamp": datetime.now(timezone.utc).isoformat(), "evidence_identity": pending["evidence_identity"]}))
    response = json.loads(complete_advisory(review.ask.call_args.args[0])[0])
    response["summary"] = "incomplete"
    for finding in response["findings"]:
        finding["assessment"] = "failed"
    review.ask.side_effect = None
    review.ask.return_value = (json.dumps(response), None)
    result, packet, _ = execute(review, evidence, decision=path)
    assert packet["deterministic_passed"] and packet["human_decision_valid"]
    assert packet["advisory_completed"]
    assert packet["advisory_review"]["summary"] == "incomplete"
    assert result and packet["release_status"] == "approved"
