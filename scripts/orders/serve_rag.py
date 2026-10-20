"""Run the existing shared RAG with an isolated validation index and audit log."""
import os
import json
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[2]
run = Path(os.environ["ORDERS_VALIDATION_RUN"]).resolve()
sys.path.insert(0, str(root / "ai-services/rag-server"))
import rag_pipeline

# Use the shared loader, embeddings, retrieval and answer generation.
# Keep a validation refresh from deleting another developer's existing index.
rag_pipeline.CHROMA_PATH = run / "rag-chroma"
rag_pipeline.AUDIT_PATH = run / "rag-audit.jsonl"
if os.getenv("ORDERS_RAG_DOCUMENTS_ONLY") == "true":
    # Explicit capture scope: never read an existing Reviews database service.
    # Both students' public Markdown still use the actual shared loader.
    rag_pipeline.build_corpus = rag_pipeline.load_knowledge_chunks

# Opt-in public-document generation trace for claim review. This wrapper records
# only Ollama generation payloads, never HTTP headers, credentials or DB records.
if os.getenv("ORDERS_RAG_CAPTURE") == "true":
    original_post = rag_pipeline.requests.post

    def traced_post(url, *args, **kwargs):
        capture = Path(os.getenv("ORDERS_RAG_CAPTURE_DIR", str(run)))
        started = time.monotonic()
        try:
            response = original_post(url, *args, **kwargs)
        except Exception as exc:
            if url == rag_pipeline.OLLAMA_BASE + "/api/generate":
                with (capture / "generation-trace.jsonl").open("a") as trace:
                    trace.write(json.dumps({"request": kwargs.get("json"), "error_type": type(exc).__name__,
                                            "elapsed_seconds": time.monotonic() - started,
                                            "timeout_seconds": kwargs.get("timeout")}) + "\n")
            raise
        if url == rag_pipeline.OLLAMA_BASE + "/api/generate":
            with (capture / "generation-trace.jsonl").open("a") as trace:
                trace.write(json.dumps({"request": kwargs.get("json"),
                                        "http": response.status_code,
                                        "elapsed_seconds": time.monotonic() - started,
                                        "timeout_seconds": kwargs.get("timeout"),
                                        "response": response.json()}) + "\n")
        return response

    rag_pipeline.requests.post = traced_post

from rag_http_server import main

if __name__ == "__main__":
    main()
