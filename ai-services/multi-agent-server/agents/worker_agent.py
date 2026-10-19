import os
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from evidence import PROVIDERS


BASE_DIR = Path(__file__).resolve().parents[1]
PROMPT_PATH = BASE_DIR / "prompts" / "worker_prompt.txt"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
WORKER_MAX_TOKENS = int(os.getenv("WORKER_MAX_TOKENS", "300"))

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",  # pragma: allowlist secret - placeholder, Ollama does not check API keys
    timeout=OLLAMA_TIMEOUT_SECONDS
)


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def format_evidence(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "No evidence found."
    return "\n".join(f"[{record['id']}] {record['text']}" for record in records)


def call_model(user_request: str, plan: str, evidence_text: str) -> str:
    prompt = f"""
{load_prompt()}

User Request:

{user_request}

Plan:

{plan}

Evidence:

{evidence_text}
"""

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=WORKER_MAX_TOKENS
        )
        return response.choices[0].message.content.strip()

    except Exception as exc:
        return (
            "Output:\n"
            "Model output could not be generated.\n\n"
            "Evidence Used:\n"
            f"{evidence_text}\n\n"
            "Limitations:\n"
            f"Model call failed. Human review required. Error: {exc}"
        )


def generate_output(user_request: str, feature: str = "student-1", plan: str = "") -> Dict[str, Any]:
    provider = PROVIDERS.get(feature)

    if provider is None:
        return {
            "status": "error",
            "agent": "worker_agent",
            "feature": feature,
            "evidence_count": 0,
            "evidence": [],
            "output": "No evidence provider is registered for this feature.",
            "human_approval_required": True
        }

    evidence = provider(user_request)

    if evidence["status"] != "success":
        return {
            "status": "error",
            "agent": "worker_agent",
            "feature": feature,
            "evidence_count": 0,
            "evidence": [],
            "output": "Feature evidence could not be retrieved.",
            "error": evidence.get("error"),
            "human_approval_required": True
        }

    records = evidence["records"]
    evidence_text = format_evidence(records)

    return {
        "status": "completed",
        "agent": "worker_agent",
        "model": OLLAMA_MODEL,
        "feature": feature,
        "evidence_source": evidence["source"],
        "evidence_count": len(records),
        "evidence": records,
        "output": call_model(user_request, plan, evidence_text),
        "human_approval_required": True
    }


if __name__ == "__main__":
    import json

    result = generate_output(
        "Summarise customer feedback for product 103.",
        plan="Objective: Summarise feedback for product 103. Steps: read the reviews, summarise them."
    )
    print(json.dumps(result, indent=2))