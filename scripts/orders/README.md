# Orders validation scripts

Run from the repository root. [Orders setup](../../student-4/README.md) describes
normal application startup. These scripts are opt-in validation tools, not runtime
services. `student-4/scripts/` retains small compatibility wrappers because saved
evidence cites those paths; new commands use this directory.

Use a separate, private directory outside the repository for each validation run:

```sh
export ORDERS_VALIDATION_RUN="$(mktemp -d "${TMPDIR:-/tmp}/orders-validation.XXXXXX")"
.venv/bin/python -m pip install -r student-4/tests/requirements.txt playwright
```

Never commit runtime.json, compose.env, login.txt, DB snapshots, session cookies,
keys or Chroma indexes. Capture scripts use installed Google Chrome in headless
mode, independently of your personal profile. The static-resource policy blocks
external images/fonts/stylesheets only; live local APIs are not mocked.

## Regression and built-image integration

```sh
AI_ENABLED=false MCP_ENABLED=false RAG_ENABLED=false \
  .venv/bin/python -m pytest student-4/tests/ -q
ORDERS_VALIDATION_RUN="$ORDERS_VALIDATION_RUN" \
  .venv/bin/python scripts/orders/local_ci.py --build
```

`local_ci.py` creates three isolated containers on an internal Docker network,
uses `RUN/image-data`, installs test dependencies inside the image and saves logs.
It removes its own containers afterwards, retaining the evidence and test DB.
Use only one `orders-image-validation` run at a time. This does not prove the
complete shared-login/team UI flow, and it does not run remote GitHub Actions.

## Fresh public-document RAG capture

Install the RAG dependencies and models in the main runbook. Ports 3004, 5004,
6004 and 8200 must be free. `rag_followup.py` needs a **nonexistent** RUN path
for its first run (unlike `local_ci.py` above):

```sh
export ORDERS_VALIDATION_RUN="${TMPDIR:-/tmp}/orders-rag-new-run"
docker build -t student4-orders:release1-local student-4
.venv/bin/python scripts/orders/rag_followup.py --capture-name coverage
```

Choose a new path/name each time; do not overwrite existing observations. Use
`--reuse` only with a runtime previously created by this collector and a new
capture name. `--include-optional` adds intentional Korean diagnostic questions;
the required nine-question English set is unchanged. A collection exits 1 when
semantic review is required; a transport/UI success alone is not correctness.

## Historical authenticated MCP/browser fixtures

`prepare.py`, `host_servers.py`, `browser_check.py`, `rag_check.py` and `audit.py`
are retained for the earlier snapshot-based validation workflow. They expect
specific existing Orders/Customers containers and a local Products database.
They are **not fresh-checkout installers**. Inspect the source names in
`prepare.py` and `audit.py`, confirm the source containers are stopped and adjust
names for your own environment before use. `prepare.py` copies source DBs into
private working fixtures and refuses to replace an existing runtime.

If the matching private runtime already exists, use its recorded configuration:

```sh
docker compose --env-file "$ORDERS_VALIDATION_RUN/compose.env" \
  -f "$ORDERS_VALIDATION_RUN/compose.json" up -d
.venv/bin/python scripts/orders/host_servers.py shared
.venv/bin/python scripts/orders/host_servers.py mcp
.venv/bin/python scripts/orders/browser_check.py
.venv/bin/python scripts/orders/audit.py
```

Start each host service only if its port is free. The browser checker writes to
fixture DBs, exercises ownership/staff/expiry/outage handling, and returns nonzero
for a recorded failure. It must not target production or personal customer data.
`audit.py` compares snapshots with the original DB hashes. Stop only that run:

```sh
.venv/bin/python scripts/orders/host_servers.py mcp stop
.venv/bin/python scripts/orders/host_servers.py shared stop
docker compose --env-file "$ORDERS_VALIDATION_RUN/compose.env" \
  -f "$ORDERS_VALIDATION_RUN/compose.json" stop
```

For saved source-based review with no new model requests, see
[Orders agentic review](../../student-4/ORDERS_AGENTIC.md). Sanitized, retained
historical results are indexed in [evidence](../../student-4/evidence/README.md).
