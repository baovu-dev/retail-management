# Orders Release 1 agentic review

The shared host loop keeps the existing `ai-mode`, `mcp` and `rag` modes.
`--feature student-4` adds Orders MCP/RAG checks; Orders does not add an AI-mode
review or a separate loop. Release 2 workflow/review modes are not implemented here.

## Review saved RAG evidence (no model calls)

From the repository root, after installing the [runbook](README.md) dependencies:

```sh
.venv/bin/python ai-services/agentic-loop/main.py --mode rag --feature student-4 \
  --evidence-file student-4/evidence/orders-final-2026-10-01/final-coverage/agentic-evidence.json \
  --review-file student-4/evidence/orders-final-2026-10-01/final-coverage/agentic-review.json
```

This validates five saved cases against an explicit source-based review and its
evidence digest. The larger nine-question matrix is in `coverage-review.json`.
It does not generate new answers or convert historical observations into a new
live-system pass. Loop output goes to ignored `ai-services/agentic-loop/outputs/`.

## Collect new evidence

With real host RAG and Orders services running:

```sh
.venv/bin/python ai-services/agentic-loop/main.py --mode rag --feature student-4 \
  --evidence-file /absolute/private/run/new-rag-evidence.json \
  --output-dir /absolute/private/run/reviews
```

Collection intentionally exits 1 with review required. Review each full answer
against its retrieved sources and supply a matching `--review-file`; do not treat
HTTP success or citations as a correctness verdict. Existing files are not overwritten.

Live MCP mode uses private fixture accounts/order IDs from
`ORDERS_VALIDATION_RUN/runtime.json`; see [validation scripts](../scripts/orders/README.md).
It checks the tool registry, owned order, other-customer denial, invalid ID, forged
token, and the backend-to-MCP path. Do not run it against arbitrary customer data.

[Retained evidence](evidence/README.md) separates the earlier RAG 3 PASS / 2 FAIL
review from the later corrected implementation's final results.
