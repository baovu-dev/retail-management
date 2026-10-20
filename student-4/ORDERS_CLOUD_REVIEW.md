# Orders Cloud Deployment Review (offline)

This is a Student 4 path in the existing shared agentic loop. Student 1 cloud
review is unchanged. This command does not contact Azure, execute deployment,
re-check a live endpoint, create test orders or make an automatic release decision.
It reviews previously collected, explicitly supplied evidence. Missing, failed,
skipped, malformed or mismatched evidence exits nonzero with a separate review
packet. Successful local tests do not establish cloud deployment or cloud bonuses.

## Current repository facts and blockers

At the implementation base `4bcb985`, the cloud workflow defaults to validation
only. Student 2 and 3 post-commit endpoint test directories are absent, and
`scripts/test/post_commit_gate.sh` correctly blocks release. Do not bypass it.
The untracked local `reports/` folder is not automatically treated as a successful
GitHub validation run. No verified group deployment is established by this work.

The current Orders frontend has no API proxy: its templates call `API_BASE`
directly from the browser. `scripts/deploy/apps.conf` gives `student4-backend`
external ingress, and `render_app_spec.py` sets the frontend API_BASE to its HTTPS
address. Review therefore requires the actual frontend origin, that public API
origin, rendered API_BASE and a successful browser/CORS API request. It never
guesses a public URL for an internal-only backend. A future frontend proxy or
ingress change must update this checker and its tests before it can pass.

The existing `deployment-results.md` reports Reviews-specific checks and accepts
an Orders backend root HTTP 404 as reachability. It supplies neither Orders CRUD
nor Orders-specific disabled-service checks. Its PASS line cannot satisfy this
review. It remains untouched. Persistence, a full authenticated browser journey,
other team features, and cloud bonus functionality remain separate unverified
claims even if the checks below eventually pass.

## Evidence inputs

Supply `--evidence-file` as a JSON bundle with the following fields. Relative
paths resolve against the bundle's directory. Do not include secrets, raw HTTP
bodies, cookies, customer records or environment files.

| Bundle field | Meaning |
| --- | --- |
| `expected_commit` | Full 40-character SHA of the release candidate under review |
| `run_file` | Saved GitHub run export with `databaseId`, `headSha`, `url`, `createdAt`, `updatedAt`, `status`, `conclusion`, `jobs` |
| `validation.metadata_file` | Saved GitHub REST metadata for `cloud-validation-tests` |
| `validation.archive_file` | Original downloaded artifact ZIP, without repacking |
| `deployment.metadata_file` | Saved GitHub REST metadata for `cloud-deployment-evidence` |
| `deployment.archive_file` | Original downloaded artifact ZIP, without repacking |

An authorized operator can export a real run with
`gh run view RUN_ID --repo baovu-dev/retail-management --json databaseId,headSha,url,createdAt,updatedAt,status,conclusion,jobs`.
Obtain artifact IDs from the run's REST artifacts listing; save each artifact's
`GET /repos/baovu-dev/retail-management/actions/artifacts/ARTIFACT_ID` JSON and
original ZIP. These are instructions for later evidence collection; this task
does not execute them. Metadata must include the correct name, `expired: false`,
`workflow_run.id`, `workflow_run.head_sha` and `digest: sha256:...`. A missing
digest is unverified, not silently accepted. Hash validation detects altered ZIPs;
offline files are not independent cryptographic attestation of GitHub authenticity.

Both jobs and the named coverage, endpoint-test, deployment and deployment-test
steps must have completed successfully. Validation-only success cannot pass.
Validation ZIP contents must include `scope.txt`, `coverage.log`, `readiness.log`
and `student-1.xml` through `student-5.xml`, matching the existing workflow/gate.
Every JUnit file requires at least two distinct non-skipped passing tests; Student
4 additionally requires its two named endpoint tests. Owners must still provide
the endpoint-function mapping for other students; a test count alone is not that
mapping. Coverage failures and mismatched readiness URLs block the review.

## Smallest missing deployment evidence change

Keep the existing Markdown report for its original purpose. Add a sanitized
`orders-cloud-evidence.json` alongside it to the **actual deployment run artifact**
and expand that workflow's deployment artifact upload path to include it. The
current script does not generate this supplement; a later authorized collector
must record real observations. This implementation neither fabricates it nor
alters the deployment workflow or Student 1 scripts to imply it already exists.

Required report fields are `feature: student-4`, `run_id` (integer), `commit_sha`
(full deployed SHA matched to the run), timezone-aware `timestamp`,
`profile: mandatory-ai-disabled`, `test_order_id` (a dedicated synthetic order),
`access`, and `checks`. Verify the deployed image actually corresponds to that
commit before recording it. Report/check timestamps must lie within the run.

`access` contains `kind: direct-public-backend`, `environment_domain` (actual
Azure Container Apps environment domain), `frontend_app: student4-frontend`,
`api_app: student4-backend`, `frontend_origin`, and `api_origin`. Origins must
match the deployed app names and environment. No credentials or query strings.

Each named `checks` entry contains `method`, actual `url`, integer `http_status`,
boolean `passed`, timezone-aware `timestamp`, and a small `observed` object.
Record the checks in this sequence; no order/customer contents are necessary:

| Check | Request | Required observation |
| --- | --- | --- |
| `frontend` | GET frontend `/`, 200 | `orders_ui_rendered: true`, `api_base` equals the API origin |
| `health` | GET API `/api/health`, 200 | `database_connected: true` |
| `count` | GET API `/api/orders/count`, 200 | Nonnegative integer `count` (zero is valid) |
| `browser_api_access` | Browser GET API `/api/orders/count`, 200 | `request_origin` at row level equals frontend; `cors_allowed: true`, integer `count` |
| `create` | POST API `/api/orders`, 201 | `order_id` matches test order; `status: PENDING` |
| `read` | GET API `/api/orders/{order_id}`, 200 | Same `order_id`; `items_preserved: true` |
| `update` | PUT API `/api/orders/{order_id}`, 200 | Same `order_id`; `status: CONFIRMED` |
| `cancel` | DELETE API `/api/orders/{order_id}`, 200 | Same `order_id`; `status: CANCELLED` |
| `read_after_cancel` | GET same order, 200 | Same ID, `status: CANCELLED`, `items_preserved: true` |
| `ai_disabled` | POST API `/api/order-assistant`, 403 | `code: disabled` |
| `mcp_disabled` | POST API `/api/mcp/order-status`, 403 | `code: disabled` |
| `rag_disabled` | POST API `/api/rag/answer`, 403 | `code: disabled` |
| `multi_agent_disabled` | POST API `/api/multi-agent/workflow`, 403 | `code: disabled` |

The supplement is an observation report, not a replacement for underlying test
execution evidence. Do not derive its results from flags, root reachability,
local mocks or manually asserted PASS labels. Future data mutation for collection
must use authorized synthetic data; cancellation retains the order and items.
Cloud AI/MCP/RAG/Multi-Agent and security bonuses require separate real evidence;
this mandatory-profile reviewer always labels bonus claims unverified.

## Run and record a human decision

Run from the repository root with a private bundle outside tracked evidence:

```sh
.venv/bin/python ai-services/agentic-loop/main.py --feature student-4 --mode cloud \
  --evidence-file /absolute/path/bundle.json --cloud-no-advisory \
  --output-dir /absolute/path/new-review-output
```

This first pass is deterministic only and never approves a release. Inspect the
separate JSON packet's checks and `evidence_identity`. To run the local Ollama
advisory, omit `--cloud-no-advisory` and configure `OLLAMA_MODEL` as appropriate.
Only allowlisted check names/results reach the model. Its response uses a bounded
JSON vocabulary; invalid prose is an incomplete advisory. Raw model text and
secret-bearing exceptions are not logged or saved. The advisory cannot override
deterministic failures or substitute for a human decision.

A person may create a separate decision JSON with `decision` (`Approve`, `Approve
with notes`, or `Reject`), `reviewer`, `reason`, timezone-aware `timestamp`, and
the exact `evidence_identity` from the packet. Use a reviewer name and a sanitized
reason without credentials or customer details. Timestamp must follow the
deployment report and not be in the future. The file is a supplied human record,
not authenticated identity proof; the responsible reviewer must author it.

Re-run with `--cloud-decision-file /absolute/path/decision.json`. The original
decision and reports are never overwritten. A new packet preserves the valid
decision separately, binds it to the evidence, and keeps release pending unless
all deterministic checks, advisory completion and explicit human approval are
present. Rejection stays rejected. Changed evidence invalidates the prior
decision. A workflow-level human correction is unrelated to this release decision.
