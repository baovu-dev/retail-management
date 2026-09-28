import json
import os
import time
import uuid
import re
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

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
# Calibrated from measured distances: relevant <= 0.323, unrelated >= 0.468
RELEVANCE_THRESHOLD = float(os.getenv("RAG_RELEVANCE_THRESHOLD", "0.40"))

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


def embed_texts(texts, prefix="search_document: "):
    """Turn texts into embeddings with nomic-embed-text.
    Documents use 'search_document: ', queries use 'search_query: '."""
    response = requests.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": EMBED_MODEL, "input": [prefix + t for t in texts]},
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

    
# ---------- Tool: retrieve_context ----------

def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        refresh_corpus()  # first run: build the index automatically
        return client.get_collection(COLLECTION_NAME)


def retrieve_context(query, k=5, feature=None):
    start = time.time()
    query = (query or "").strip()
    if not query:
        return {"status": "error", "error": "query is required"}
    k = max(1, min(int(k), 10))

    try:
        collection = get_collection()
        results = collection.query(
            query_embeddings=embed_texts([query], prefix="search_query: "),
            n_results=k,
            where={"feature": feature} if feature else None,
        )

        ranked = []
        for i, chunk_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            ranked.append({
                "rank": i + 1,
                "chunk_id": chunk_id,
                "source_id": meta.get("source_id"),
                "authority_tier": meta.get("authority_tier"),
                "feature": meta.get("feature"),
                "distance": round(results["distances"][0][i], 4),
                "text": results["documents"][0][i],
            })

        output = {"status": "success", "query": query, "k": k, "feature": feature, "results": ranked}
        append_audit("retrieve_context", {"query": query, "k": k, "feature": feature},
                     {"result_count": len(ranked), "chunk_ids": [r["chunk_id"] for r in ranked]},
                     "success", start)
        return output
    except Exception as exc:
        output = {"status": "error", "error": str(exc), "query": query}
        append_audit("retrieve_context", {"query": query, "k": k}, output, "error", start)
        return output

    # ---------- Tool: answer_question ----------

ANSWER_PROMPT = """You are the KICKLAB assistant.
Answer the question using ONLY the numbered context below.
After each fact, cite its source number in square brackets, for example [1].
If the context does not contain the answer, reply exactly: Insufficient context.
Keep the answer under 80 words.

QUESTION:
{question}

CONTEXT:
{context}
"""

INSUFFICIENT_MESSAGE = "Insufficient context: no relevant KICKLAB information was found for this question."


def confidence_from_distance(best_distance):
    if best_distance is None or best_distance > RELEVANCE_THRESHOLD:
        return "Insufficient"
    if best_distance <= 0.28:
        return "High"
    if best_distance <= 0.35:
        return "Medium"
    return "Low"


def _generate(prompt):
    try:
        response = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0}},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["response"].strip(), None
    except Exception as exc:
        return None, str(exc)


def answer_question(query, k=5, feature=None):
    start = time.time()
    retrieval = retrieve_context(query, k, feature)
    if retrieval["status"] != "success":
        return {"status": "error", "query": query, "error": retrieval.get("error")}

    results = retrieval["results"]
    best = results[0]["distance"] if results else None
    relevant = [r for r in results if r["distance"] <= RELEVANCE_THRESHOLD]
    summary = {
        "k": k,
        "retrieved_count": len(results),
        "relevant_count": len(relevant),
        "best_distance": best,
        "threshold": RELEVANCE_THRESHOLD,
    }

    def insufficient(reason):
        output = {
            "status": "insufficient_context",
            "query": query,
            "answer": INSUFFICIENT_MESSAGE,
            "citations": [],
            "confidence_category": "Insufficient",
            "retrieval_summary": {**summary, "reason": reason},
        }
        append_audit("answer_question", {"query": query, "feature": feature},
                     {"confidence_category": "Insufficient", "reason": reason},
                     "insufficient_context", start)
        return output

    # Layer 1: deterministic relevance check, no LLM call
    if not relevant:
        return insufficient("no chunk within relevance threshold")

    context = "\n".join(f"[{i}] {r['text']}" for i, r in enumerate(relevant, start=1))
    reply, error = _generate(ANSWER_PROMPT.format(question=query, context=context))
    if error:
        return {"status": "error", "query": query, "error": f"Ollama unavailable: {error}"}

    # Layer 2: the model itself found the context insufficient
    if reply.lower().startswith("insufficient context"):
        return insufficient("model found context insufficient")

        # Keep only the sources the answer actually cites, e.g. [1], [2]
    used_refs = {int(n) for n in re.findall(r"\[(\d+)\]", reply)}
    citations = [
        {"ref": i, "source_id": r["source_id"], "chunk_id": r["chunk_id"],
         "authority_tier": r["authority_tier"], "distance": r["distance"]}
        for i, r in enumerate(relevant, start=1)
        if i in used_refs
    ]
    if not citations:
        # Model gave no [n] references; fall back to all relevant context
        citations = [
            {"ref": i, "source_id": r["source_id"], "chunk_id": r["chunk_id"],
             "authority_tier": r["authority_tier"], "distance": r["distance"]}
            for i, r in enumerate(relevant, start=1)
        ]
    summary["cited_count"] = len(citations)
    confidence = confidence_from_distance(best)
    output = {
        "status": "success",
        "query": query,
        "answer": reply,
        "citations": citations,
        "confidence_category": confidence,
        "retrieval_summary": summary,
    }
    append_audit("answer_question", {"query": query, "feature": feature},
                 {"confidence_category": confidence, "citation_count": len(citations)},
                 "success", start)
    return output


if __name__ == "__main__":
    print(json.dumps(refresh_corpus(), indent=2))

    for q in [
        "When does a review get flagged?",
        "What do customers say about product 103?",
        "What is the weather in Paris today?",
    ]:
        print("\n" + "=" * 60)
        print(json.dumps(answer_question(q, k=5, feature="student-1"), indent=2))