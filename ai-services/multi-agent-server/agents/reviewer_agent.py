import json
import os
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parents[1]
PROMPT_PATH = BASE_DIR / "prompts" / "reviewer_prompt.txt"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_REVIEW_MODEL = os.getenv("OLLAMA_REVIEW_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
REVIEWER_MAX_TOKENS = int(os.getenv("REVIEWER_MAX_TOKENS", "200"))

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",  # pragma: allowlist secret - placeholder, Ollama does not check API keys
    timeout=OLLAMA_TIMEOUT_SECONDS,
    max_retries=0,
)


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def call_model(user_request: str, plan: str, worker_result: Dict[str, Any]) -> str:
    orders_scope = """
For student-4 Orders, the plan is not evidence. The Worker receives only the
aggregate count and the two cited public guidance documents. Check claims
against those records. Do not penalize the Worker for explicitly identifying
missing individual-order data or for declining to make unsupported claims.
If the Planner requests unavailable records or tables, identify that as a
planning limitation rather than claiming that the Worker invented facts.
""" if worker_result.get("feature") == "student-4" else ""
    prompt = f"""
{load_prompt()}

User Request:

{user_request}

Plan:

{plan}

Worker Result:

{json.dumps(worker_result, indent=2)}

{orders_scope}
"""

    try:
        response = client.chat.completions.create(
            model=OLLAMA_REVIEW_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=REVIEWER_MAX_TOKENS
        )
        return response.choices[0].message.content.strip()

    except Exception as exc:
        raise RuntimeError("Reviewer model unavailable") from exc


def review_output(user_request: str, worker_result: Dict[str, Any], plan: str = "") -> Dict[str, Any]:
    try:
        review = call_model(user_request, plan, worker_result)
    except RuntimeError:
        return {"status": "error", "agent": "reviewer_agent", "model": OLLAMA_REVIEW_MODEL,
                "review": "", "error": "Reviewer model unavailable",
                "human_approval_required": True}
    return {
        "status": "completed",
        "agent": "reviewer_agent",
        "model": OLLAMA_REVIEW_MODEL,
        "review": review,
        "human_approval_required": True
    }


if __name__ == "__main__":
    sample_worker_result = {
        "status": "completed",
        "feature": "student-1",
        "evidence_count": 2,
        "evidence": [
            {"id": "review 5", "text": "product 103, rating 5/5, comment: \"Exceeded my expectations!\""},
            {"id": "review 6", "text": "product 103, rating 1/5, comment: \"Terrible, do not buy.\""}
        ],
        "output": "Product 103 has mixed feedback: one 5-star review [review 5] and one 1-star review [review 6]."
    }

    result = review_output(
        "Summarise customer feedback for product 103.",
        sample_worker_result,
        plan="Objective: Summarise feedback for product 103."
    )
    print(json.dumps(result, indent=2))
