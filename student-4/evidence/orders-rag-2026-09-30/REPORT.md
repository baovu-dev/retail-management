# Historical Orders RAG browser validation — 2026-09-30

[Results](rag-results.json) record **11 PASS / 0 FAIL** after correcting the browser
assertion's DOM-text normalization. The [initial failed run](initial-ui-assertion-failure.json)
is retained. This small question set used real local RAG/Ollama and an isolated
index; it does not establish general answer correctness. Later claim review found
two failures, retained in the [agentic summary](../orders-agentic-ci-2026-09-30/SUMMARY.json).

Success, insufficient-context and outage screenshots and original DB-preservation
hashes remain in this folder. See the [evidence index](../README.md) for final
nine-question coverage. Current commands are in the [Orders runbook](../../README.md).
This English summary replaces the original prose preserved in baseline `7e25183`
and the external archive. Raw observations were not modified.
