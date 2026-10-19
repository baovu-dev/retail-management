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
    timeout=OLLAMA_TIMEOUT_SECONDS
)


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def call_model(user_request: str, plan: str, worker_result: Dict[str, Any]) -> str:
    prompt = f"""
{load_prompt()}

User Request:

{user_request}

Plan:

{plan}

Worker Result:

{json.dumps(worker_result, indent=2)}
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
        return (
            "Risk: Review model unavailable.\n"
            "Correction: Verify Ollama and the reviewer model.\n"
            "Retest: Run the workflow again.\n"
            f"Recommendation: Do not approve until reviewed. Error: {exc}"
        )


def review_output(user_request: str, worker_result: Dict[str, Any], plan: str = "") -> Dict[str, Any]:
    return {
        "status": "completed",
        "agent": "reviewer_agent",
        "model": OLLAMA_REVIEW_MODEL,
        "review": call_model(user_request, plan, worker_result),
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