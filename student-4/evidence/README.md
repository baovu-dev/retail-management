# Orders Release 1 evidence

Latest cleanup validation: [2026-10-09 report](orders-cleanup-2026-10-09/REPORT.md).

The earlier folders are retained historical observations, not results for every later commit.
Raw responses, review decisions and validation logs are kept unchanged. Current
setup belongs in the [Orders runbook](../README.md), not in old execution reports.

| Evidence | Scope |
| --- | --- |
| [MCP browser results](orders-mcp-2026-09-30/browser-results.json) | 23 PASS: shared login, ownership/staff boundaries, token expiry, outage/recovery; screenshots and DB preservation hashes in the same directory |
| [MCP agentic log](orders-agentic-ci-2026-09-30/student-4-mcp-20260930-131619-459844.txt) | 6 PASS for actual shared MCP/backend calls |
| [Final RAG coverage review](orders-final-2026-10-01/final-coverage/coverage-review.json) | Nine English questions, source review, 9/9 UI checks and outage behavior; finite local coverage only |
| [Final RAG browser observations](orders-final-2026-10-01/final-coverage/browser-evidence.json) | Full answers, retrieved grounds and timing; screenshots and model trace retained beside this file |
| [Final agentic review](orders-final-2026-10-01/final-coverage/agentic-review.json) and [log](orders-final-2026-10-01/final-coverage/student-4-rag-20261001-203725-738742.txt) | Five saved cases with review bound to the evidence digest |
| [Final historical regression](orders-final-2026-10-01/ci-python311-coverage.log) | 156 passed, 1 optional live test skipped, Python 3.11; not a remote CI run |
| [Earlier RAG review](orders-agentic-ci-2026-09-30/SUMMARY.json) | 3 PASS / 2 FAIL retained alongside the original evidence and review; those failures have not been relabeled |
| [Earlier browser assertion failure](orders-rag-2026-09-30/initial-ui-assertion-failure.json) and [subsequent result](orders-rag-2026-09-30/rag-results.json) | Original DOM-text assertion issue and later 11 PASS run; this smaller set predates final nine-question coverage |

The 2026-10-08 cleanup archived seven repeated `attempt-*` directories, exploratory
`*-probe*` outputs, the superseded September 29 MCP capture, the interim follow-up
folder, and duplicate CI logs. The baseline is Git commit `7e25183`; all original
tracked files and Git history were also exported outside the repository before
removal. Use Git history to retrieve an omitted experiment. No runtime knowledge,
application tests or team-owned evidence under `docs/` was removed.

Historical English summaries replace the old Korean prose reports; original prose
is in the baseline/archive. Korean text inside original model/reviewer records and
optional multilingual test questions is intentional and retained. Historical paths,
model versions and commit references describe the original run. They are not current
startup instructions. Complete five-feature acceptance and Release 2 are separate
from these Orders-specific records.
