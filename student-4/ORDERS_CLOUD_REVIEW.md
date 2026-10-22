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

## Deployment evidence integration still required

Keep the existing Markdown report for its original purpose. Add a sanitized
`orders-cloud-evidence.json` alongside it to the **actual deployment run artifact**
and expand that workflow's deployment artifact upload path to include it. The
shared deployment script does not invoke the collector yet. The Orders collector
below records real observations only during an explicitly authorized future run.
It is not wired into deployment by this change; Student 1 scripts remain unchanged.

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


## Orders cloud collector: prerequisites and safe execution

`scripts/orders/cloud_evidence.py` creates a new, private `orders-cloud-evidence.json`
with the exact core fields/check names above. Additional bounded fields are
`collector: orders-cloud-http-v1`, a unique `collection_id`, `collection_status`,
`deployment_config_sha256`, `retention`, `limitations`, and three denial checks:
`unauthenticated_create_denied`, `invalid_credential_denied`, `ownership_denied`.
These checks use the same row format. Their observations contain only
`access_denied: true/false`. The reviewer rejects marked collector reports with
failed collection status or missing/failed denial checks, even if core rows pass.
No raw request headers, cookies, response bodies, customer IDs/names/emails or
exception strings are written. The dedicated synthetic order ID is retained for
traceability and manual cleanup. HTTP response reads are limited to 64 KiB.

**Authentication implementation:** Orders CRUD now verifies dedicated signed
shared-session capabilities and enforces customer ownership and staff actions.
See [the CRUD contract](ORDERS_CRUD_AUTH.md). The collector's anonymous and forged
probes still run before authenticated creation. An old/misconfigured deployment
continues to fail closed; implementing this source does not prove it is deployed.
Shared-store login cookies are used only at shared login; MCP/review tokens cannot
authorize CRUD and mandatory-profile MCP stays disabled.

Use three distinct real shared-login accounts: an approved synthetic owner, a
second unrelated synthetic customer, and staff. The collector can mint fresh
120-second CRUD credentials through their shared sessions for each protected
operation. It checks returned role and owner/other customer IDs. The staff account
must use the configured private password. No signing key is needed by the tool.
Alternatively provide recently minted actual CRUD bearer credentials, accepting
that expiry causes a failed run rather than an automatic mutation retry.

Supply a private mode-0600 JSON credential file (never commit or pass tokens in
command arguments). Preferred mode uses `owner.email`, `owner.password`,
`owner.customer_id`, equivalent `other` fields and `staff.email`, `staff.password`;
add `shared_origin: https://shared-backend.<environment_domain>` to the deployment
config. Existing bearer mode fields are `owner.bearer_token`, `owner.customer_id`,
`other.bearer_token`, `other.customer_id`, and `staff.bearer_token`. Both customer
IDs must be distinct positive IDs for explicitly approved synthetic accounts.
The owner creates/reads; staff confirms/cancels; the other credential must receive
403/forbidden when reading that exact newly created order. A 401, generic 403,
404, or a successful read cannot establish ownership denial.

Supply an operator-verified deployment JSON with `run_id`, full `commit_sha`,
`environment_domain`, `frontend_origin`, `api_origin`, and `images`. The images
map contains `student4-frontend` and `student4-backend`, each the actual deployed
`<registry>.azurecr.io/student-4:<commit-tag>` reference. Tags must match a prefix
of at least seven characters of the full SHA. Use the actual environment domain;
origins must be exactly `https://student4-frontend.<environment_domain>` and
`https://student4-backend.<environment_domain>`, without ports, queries or
credentials. Localhost, local Docker, internal-only origins, redirects, private
DNS results and unrelated HTTPS origins are rejected. TLS verification stays on;
ambient proxy/netrc settings are disabled. Never repack local Docker results as
cloud evidence. The collector validates supplied image/SHA consistency, not image
content authenticity: the deployment owner must verify revision/image-to-commit
mapping and retain that source evidence. It never contacts the Azure control plane.

Coordinate with the deployment owner before choosing the run ID, SHA and timing.
To meet the offline reviewer's run-window rule and artifact digest verification,
collection must occur within the same authorized deployment workflow run and be
uploaded alongside the existing report in that run's deployment artifact. An
independent later manual run is diagnostic evidence; it must not be relabelled
as evidence from an already completed workflow. Do not enable deployment or
bypass Student 2/3 validation to run this collector.

The browser probe requires Playwright and its Chromium runtime (install separately
with `python -m pip install playwright` and `python -m playwright install chromium`
in the intended collection environment). It opens the actual frontend in a fresh
context and fetches only the public count endpoint from that origin. Other API
calls, third-party resources and service workers are blocked in that browser.
An HTTP request carrying an Origin header is never substituted for a real browser
CORS result. No browser screenshots, customer pages or HAR files are saved.

For a later **explicitly authorized** run only (not executed during implementation):

```sh
.venv/bin/python scripts/orders/cloud_evidence.py \
  --deployment-file /private/run/deployed-config.json \
  --credentials-file /private/run/api-credentials.json \
  --product-id SYNTHETIC_PRODUCT_ID --unit-price APPROVED_TEST_PRICE \
  --output /private/run/orders-cloud-evidence.json --allow-test-order
```

The output parent directory must already exist. Existing output files are refused
before network access. `--allow-test-order` explicitly authorizes one fresh POST;
there is no retry of create or any other mutation. Use a dedicated approved test
product/price with quantity one. The database generates a fresh order ID, tied to
the unique collection ID. Inspect that exact order's ID, owner, one item, price,
status and total in memory before any staff mutation; customer data is discarded
from the report. A second uncached read on a new connection after cancellation
checks the retained cancelled state/items after a short delay. This proves
request-level retention only, **not** persistence across restart/redeployment.
No resource restart is performed. Separate authorized restart evidence remains
necessary before claiming that stronger property.

Failures exit nonzero and retain a failed/partial report. The current blocked
implementation produces no successful Orders cloud claim. On a create timeout,
an order may exist without a known ID: reconcile only the synthetic account
privately before retrying; do not blindly rerun. After successful cancellation,
the order and items remain stored and may affect team counts. On later failure,
an order may remain PENDING or CONFIRMED. The report retains the known ID and
manual-retention warning. No automatic physical deletion, database reset or volume
cleanup is performed. Agree on retention/cleanup with the team before collection.
No live collection, cloud deployment, bonus validation or release approval occurs
as part of adding or mock-testing this tool.
