import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import requests

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CHROMA_PATH = BASE_DIR / "chroma"
AUDIT_PATH = BASE_DIR / "rag-audit.jsonl"
COLLECTION_NAME = "kicklab_context"

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
REVIEWS_DB_API = os.getenv("REVIEWS_DB_API", "http://localhost:6001")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_audit(action, tool_input, tool_output, outcome, start_time):
    record = {
        "request_id": str(uuid.uuid4()),
        "action": action,
        "input": tool_input,
        "output": tool_output,
        "outcome": outcome,
        "timestamp": now_iso(),
        "duration_ms": int((time.time() - start_time) * 1000),
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def embed_texts(texts):
    """Turn a list of texts into embeddings using Ollama's nomic-embed-text."""
    response = requests.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def chunk_text(text, max_words=80):
    words = text.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


# ---------- Corpus sources ----------

def load_knowledge_chunks():
    """Tier 2: markdown/text docs in knowledge/<feature>/."""
    chunks = []
    for path in sorted(KNOWLEDGE_DIR.glob("*/*")):
        if path.suffix not in (".md", ".txt"):
            continue
        feature = path.parent.name
        source_id = f"knowledge/{feature}/{path.name}"
        text = path.read_text(encoding="utf-8")
        for i, chunk in enumerate(chunk_text(text), start=1):
            chunks.append({
                "chunk_id": f"{source_id}#{i}",
                "source_id": source_id,
                "authority_tier": "tier_2",
                "feature": feature,
                "text": chunk,
            })
    return chunks


def load_review_chunks():
    """Tier 1: live reviews from the Student 1 reviews database API."""
    try:
        response = requests.get(f"{REVIEWS_DB_API}/reviews", timeout=10)
        response.raise_for_status()
        reviews = response.json()
    except requests.RequestException:
        return []

    chunks = []
    for r in reviews:
        flagged = "yes" if r.get("is_flagged") else "no"
        text = (
            f"Review {r['review_id']} for product {r['product_id']}: "
            f"rating {r['rating']} out of 5. Comment: {r.get('comment') or 'none'}. "
            f"Flagged for moderation: {flagged}."
        )
        chunks.append({
            "chunk_id": f"student-1:review/{r['review_id']}",
            "source_id": f"reviews-db:review/{r['review_id']}",
            "authority_tier": "tier_1",
            "feature": "student-1",
            "text": text,
        })
    return chunks


def build_corpus():
    return load_review_chunks() + load_knowledge_chunks()


# ---------- Tool: refresh_corpus ----------

def refresh_corpus():
    start = time.time()
    try:
        chunks = build_corpus()
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        # cosine distance: 0 = identical meaning, larger = less related
        collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

        if chunks:
            collection.add(
                ids=[c["chunk_id"] for c in chunks],
                documents=[c["text"] for c in chunks],
                metadatas=[
                    {"source_id": c["source_id"], "authority_tier": c["authority_tier"], "feature": c["feature"]}
                    for c in chunks
                ],
                embeddings=embed_texts([c["text"] for c in chunks]),
            )

        output = {
            "status": "success",
            "chunk_count": len(chunks),
            "tier_1_chunks": sum(1 for c in chunks if c["authority_tier"] == "tier_1"),
            "tier_2_chunks": sum(1 for c in chunks if c["authority_tier"] == "tier_2"),
            "collection": COLLECTION_NAME,
        }
        append_audit("refresh_corpus", {}, output, "success", start)
        return output
    except Exception as exc:
        output = {"status": "error", "error": str(exc)}
        append_audit("refresh_corpus", {}, output, "error", start)
        return output


if __name__ == "__main__":
    print(json.dumps(refresh_corpus(), indent=2))