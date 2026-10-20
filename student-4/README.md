# Orders — Release 1

Orders is part of the shared KICKLAB application. Keep the existing CRUD, AI
assistant, authenticated read-only MCP status lookup, and documentation RAG.
The desktop UI follows `shared/frontend/css/styles.css` (Outfit, colours, logo,
buttons and cards); its local stylesheet also works when Orders runs separately.

## Requirements and service addresses

Use Docker Desktop / Docker Compose and Python 3.11 for the documented checks.
Run commands below from the repository root. Open the site using **localhost**
consistently; the shared login cookie and MCP origin check depend on this.

| Service | Browser/host address | Container-to-container address |
| --- | --- | --- |
| Shared home and login | http://localhost:5000 | `http://shared-backend:5000` |
| Orders UI / staff UI | http://localhost:3004 / http://localhost:3004/admin | — |
| Orders API | http://localhost:5004 | `http://student4-backend:5004` |
| Orders database API | http://localhost:6004 | `http://student4-database:6004` |
| Customers API | http://localhost:5003 | `http://student3-backend:5003` |
| Products API | http://localhost:5002 | `http://student2-backend:5002` |
| Host MCP / RAG | http://localhost:8100/mcp / http://localhost:8200 | `host.docker.internal:8100` / `:8200` |
| Host Ollama | http://localhost:11434 | `host.docker.internal:11434` |

Docker Desktop supplies `host.docker.internal`. Native Linux needs an equivalent
host-gateway mapping. MCP, RAG, Ollama and the agentic loop run on the host, outside
Compose. Only start one root or standalone Orders stack on the default ports.

## Prepare local configuration

Create a root `.env` without overwriting existing settings. The generated values
stay private and are ignored by Git; shared login and Orders must use the same
`ORDERS_MCP_SECRET`. Keep an existing `.env` and add missing settings manually.

```sh
python3 - <<'PY'
from pathlib import Path
import secrets
path = Path('.env')
with path.open('x') as out:
    path.chmod(0o600)
    for name in ('SECRET_KEY', 'ORDERS_MCP_SECRET', 'STAFF_PASSWORD'):
        out.write(f'{name}={secrets.token_hex(32)}\n')
    out.write('STAFF_EMAIL=admin@kicklab.com\nAI_ENABLED=true\nMCP_ENABLED=true\nRAG_ENABLED=true\n')
PY
```

The staff password is in this private file. Register a customer through the shared
site; do not rely on old demo account credentials. MCP fails closed if secrets
are missing/too short, or the default staff password is still in use.

## Start the local application

**Existing installation:** back up Orders before recreating its old database
container. The new named volume does not import an old container's database
automatically. See [existing data](#existing-data-and-demo-seeding) first.

For a fresh disposable checkout, root Compose now includes shared login:

```sh
docker compose config --quiet
docker compose up -d --build
```

The Reviews and Customers services still run their owners' seed initializers on
startup. Check with those owners before restarting a stack that contains data you
need to retain. Do not reuse someone else's database for validation.

For an Orders-only launch (shared login/customer/product services must already
be available for the corresponding flows):

```sh
docker compose --env-file .env -f student-4/docker-compose.yml up -d --build
```

The root and standalone projects have separate Orders volumes. Use the same
project consistently. Stop with `docker compose stop`; avoid `down -v` when
retaining data.

## Start the host AI services

Prepare a host environment once:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r student-4/tests/requirements.txt \
  -r ai-services/rag-server/requirements.txt -r ai-services/agentic-loop/requirements.txt
ollama pull qwen2.5:0.5b
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

Other team features use `llama3.1:8b`; pull it too for their AI paths. Keep one
Ollama server running (`ollama serve` if the desktop app is not already serving).
Start these in separate terminals from the repository root:

```sh
# Terminal 1: shared MCP; calls back to the host-published Orders API.
ORDERS_API_URL=http://localhost:5004 .venv/bin/python ai-services/mcp-server/server.py
```

```sh
# Terminal 2: shared RAG; Orders uses its own model selection in this server.
ORDERS_RAG_MODEL=qwen2.5:3b .venv/bin/python ai-services/rag-server/rag_http_server.py
```

After a fresh RAG setup or a deliberate knowledge update, refresh the shared
index once. This replaces the index, so coordinate with anyone using that server:

```sh
curl --fail -X POST http://localhost:8200/refresh
```

Keep `ai-services/rag-server/knowledge/student-4/*.md`: these are runtime RAG input,
not disposable reports. The guide uses public documentation, not customer orders.
Confidence describes retrieval similarity, not a probability that an answer is
correct. Missing delivery/refund facts should produce insufficient context.

Orders backend settings: `AI_ENABLED` (default true), `MCP_ENABLED` and
`RAG_ENABLED` (default false), `OLLAMA_URL`, `OLLAMA_MODEL` (`qwen2.5:0.5b`),
`MCP_URL`, `RAG_URL`, and `ORDERS_MCP_SECRET`. The host RAG server separately reads
`ORDERS_RAG_MODEL` (`qwen2.5:3b`), `EMBED_MODEL` (`nomic-embed-text`) and
`OLLAMA_BASE_URL`. These defaults describe Release 1 local use, not a cloud profile.

## Check the integrated user flow

1. Open http://localhost:5000, register/log in, then use the store to place an order.
2. Follow **My Orders** from the shared home. The customer ID filters the order list.
3. Open order details and cancel a test order. Cancellation retains the order and
   its items. Staff can also confirm an order via the dashboard's Orders link.
4. Ask the AI assistant about a known order ID.
5. Check that same order using MCP while logged in. Its short-lived capability
   verifies the signed identity, order scope, expiry and ownership.
6. Ask the Orders guide about statuses and cancellation; inspect sources. Ask an
   undocumented delivery/refund timing question and verify insufficient context.

Release 1's legacy CRUD/customer-id filter is not an authorization boundary.
The stronger identity/ownership checks described here apply to MCP; this cleanup
does not claim to add authorization to the existing CRUD routes.

## Existing data and demo seeding

Normal Orders startup creates missing tables only. `ORDERS_DB_PATH` selects the
SQLite file; Compose sets it to `/app/data/orders.db` in the `orders-data` volume.
A new database starts empty; create orders through the store.

To migrate an existing root installation, **before the first update**, stop its
Orders backend/database, copy `/app/database/orders.db` from the old database
container to a private backup directory, and verify the backup. For example:

```sh
docker compose stop student4-backend student4-database
# Replace OLD_CONTAINER and /absolute/private/path with your actual values.
docker cp OLD_CONTAINER:/app/database/orders.db /absolute/private/path/orders.db
```

Then build the new image and import into an empty named volume, refusing an
existing target. The source path must be a directory containing the backup:

```sh
docker compose build student4-database
docker compose run --rm --no-deps \
  -v /absolute/private/path:/backup:ro student4-database python -c \
  'from pathlib import Path; p=Path("/app/data/orders.db"); p.parent.mkdir(parents=True,exist_ok=True); source=Path("/backup/orders.db").read_bytes(); f=p.open("xb"); f.write(source); f.close()'
docker compose up -d student4-database student4-backend student4-frontend
```

For standalone Compose, use its `-f`/`--env-file` options and `database`/`backend`/
`frontend` service names. The original backup is retained.

Demo seeding is optional and explicit. It refuses a database containing orders:

```sh
docker compose stop student4-backend student4-database
docker compose run --rm --no-deps student4-database python database/init_db.py --seed-demo
docker compose up -d student4-database student4-backend
```

Only for a disposable database, append `--reset` to intentionally replace all
orders/items. Demo product IDs are synthetic; store-created orders use real product
IDs. Running `python database/init_db.py` without flags never seeds or clears data.

## Tests and evidence

```sh
.venv/bin/python -m pip install -r student-4/tests/requirements.txt
AI_ENABLED=false MCP_ENABLED=false RAG_ENABLED=false \
  .venv/bin/python -m pytest student-4/tests/ -q
RUN_ORDERS_MCP_LIVE=1 .venv/bin/python -m pytest student-4/tests/test_orders_mcp_live.py -q
docker compose config --quiet
docker compose -f student-4/docker-compose.yml config --quiet
```

The default tests use temporary databases/mocked external calls; the opt-in MCP
test runs real local HTTP/MCP with an isolated fixture, not the complete group app.
The existing `.github/workflows/student-4-ci.yml` runs tests and Docker validation.
See [validation scripts](../scripts/orders/README.md), [agentic review](ORDERS_AGENTIC.md)
and [retained evidence](evidence/README.md) for scope and historical limitations.
