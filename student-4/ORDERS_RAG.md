# Orders RAG

Use the [Orders runbook](README.md) for host setup, models, index refresh and UI
checks. Orders calls the existing shared RAG server with `feature=student-4`.
Its public knowledge lives in `ai-services/rag-server/knowledge/student-4/`.

The backend distinguishes success, insufficient context, disabled service,
unavailable service and invalid upstream responses. The UI shows the answer,
source/chunk identifiers and retrieval confidence. Related documentation alone
does not prove the requested fact exists; delivery/refund timing is undocumented.

[Final retained evidence](evidence/README.md) includes nine questions, source review,
an outage check and the corresponding agentic review. Finite local results are
not proof that every question or every team feature works. See
[validation scripts](../scripts/orders/README.md) for isolated capture commands.
