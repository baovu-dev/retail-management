# Project validation entry points

Run from the repository root. Feature-owned implementations stay in
`scripts/orders/` so their import paths and existing commands remain compatible.

- Orders regression: `python -m pytest student-4/tests/ -q`
- Compose (no expanded secrets): `docker compose config --quiet`
- Orders image/CI: `python scripts/orders/local_ci.py` (private RUN required)
- Shared loop: `python ai-services/agentic-loop/main.py --help`
- Public-document RAG browser capture: see
  [Orders runbook](../student-4/README.md).

No cloud deployment workflow is part of Release 1.
