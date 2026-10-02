# Local Orders validation

Current fresh-checkout and --reuse procedure:
[handoff](../../docs/release-1/student-4/README.md).
`rag_followup.py` captures actual UI/HTTP/model evidence; exit 1 means review required.
Its canonical implementation is here; old student-4/scripts commands forward here.

These scripts contain no runtime credentials or databases. They use a private
directory **outside this repository** selected by `ORDERS_VALIDATION_RUN`.
Do not add that directory, `runtime.json`, `compose.env`, `login.txt`, DB copies,
or browser cookies/tokens to Git. Use a separate Python environment:

```sh
python -m pip install -r student-4/tests/requirements.txt playwright
export ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation
```

The browser checker uses installed Google Chrome (`channel='chrome'`). Its
headless context is independent of your personal Chrome profile.

For the already prepared validation environment, **reuse** its runtime and DBs:

```sh
docker compose --env-file "$ORDERS_VALIDATION_RUN/compose.env" -f "$ORDERS_VALIDATION_RUN/compose.json" ps
# If stopped, start only this dedicated project (commands do not run init_db.py):
docker compose --env-file "$ORDERS_VALIDATION_RUN/compose.env" -f "$ORDERS_VALIDATION_RUN/compose.json" up -d
# Run these only when the corresponding validation server is stopped:
python scripts/orders/host_servers.py shared
python scripts/orders/host_servers.py mcp
python scripts/orders/browser_check.py
python scripts/orders/audit.py
```

Orders RAG validation is separate from the completed MCP checks. Install the
existing `ai-services/rag-server/requirements.txt` on the host and pull
`nomic-embed-text` in Ollama. With the same RUN, start `host_servers.py rag`, then
run `rag_check.py`. It uses an isolated index and the same real shared pipeline.
See `student-4/ORDERS_RAG.md` for configuration and expected results. Stop it with
`host_servers.py rag stop`; do not remove or regenerate runtime files.

For shared agentic-loop Orders cases and source-by-source RAG answer review, see
`student-4/ORDERS_AGENTIC.md`. Collection alone is not a correctness pass. Existing
related-unknown delivery/refund observations remain failed and are preserved.
For default Dockerfile/Python 3.11/local CI checks, build the image as documented
there, then run `local_ci.py`. It creates only a separate internal test network and
new `RUN/image-data` database; it does not change this browser validation stack.

`browser_check.py` exits 1 on exceptions **or any recorded FAIL**. The normal,
recovery and fresh-token checks require the exact requested ID, PENDING state,
MCP tool/source and matching screen text. Use its dedicated PENDING fixture order;
do not change that fixture's status manually. Other test orders are created,
confirmed and cancelled only in the working DB copies. It temporarily stops and
restarts the validation MCP process and waits for real token expiry.

Network policy: only external `image`, `font`, and `stylesheet` resources are
aborted. All localhost/loopback/host.docker.internal requests are allowed, and
fetch/XHR/API requests are never fulfilled with mock responses or blocked by
this policy. The first historical browser run had a broader non-local URL block;
current runs use this explicit static-only policy.

On a fresh environment only, inspect `prepare.py` source DB/container names and
ensure ports 3004, 5000, 5003, 5004, 5102, 6002, 6003, 6004, 8100 are available.
The script reads snapshots from stopped Orders/Customer containers and a local
Product DB. It generates independent working copies and random test credentials,
and refuses to overwrite an existing runtime:

```sh
python scripts/orders/prepare.py
docker build -t orders-mcp-validation:local -f "$ORDERS_VALIDATION_RUN/Dockerfile" .
```

Do not rerun preparation after partial failure without inspecting existing files.
`host_servers.py` reads private settings, and `audit.py` compares original DB
hashes without printing secrets. Reports and screenshots land in RUN. Review them
before copying sanitized evidence into `student-4/evidence/`.

Stop only validation services without deleting data:

```sh
python scripts/orders/host_servers.py mcp stop
python scripts/orders/host_servers.py shared stop
docker compose --env-file "$ORDERS_VALIDATION_RUN/compose.env" -f "$ORDERS_VALIDATION_RUN/compose.json" stop
```
