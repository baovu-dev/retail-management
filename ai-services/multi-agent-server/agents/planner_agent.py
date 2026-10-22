import os
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parents[1]
PROMPT_PATH = BASE_DIR / "prompts" / "planner_prompt.txt"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
PLANNER_MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "200"))

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",  # pragma: allowlist secret - placeholder, Ollama does not check API keys
    timeout=OLLAMA_TIMEOUT_SECONDS,
    max_retries=0,
)


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def default_steps() -> List[Dict[str, Any]]:
    return [
        {"step": 1, "agent": "planner_agent", "action": "Create workflow plan"},
        {"step": 2, "agent": "worker_agent", "action": "Retrieve feature evidence through the database API and generate output"},
        {"step": 3, "agent": "reviewer_agent", "action": "Review output against the plan and evidence"},
        {"step": 4, "agent": "human_reviewer", "action": "Approve, correct, partially accept, or reject"}
    ]


def call_model(user_request: str, feature: str) -> str:
    orders_scope = """
Available evidence for student-4 Orders:
- A live aggregate total order count, with no customer or individual order records.
- knowledge/student-4/order-statuses.md (supported status rules).
- knowledge/student-4/order-cancellation.md (cancellation rules).
Plan only work these sources can support. An Orders table query, individual status,
customer-specific count, or CancellationRules table is not available to the Worker.
The feature name student-4 identifies a service, not a customer.
""" if feature == "student-4" else ""
    prompt = f"""
{load_prompt()}

Feature:

{feature}

{orders_scope}

User Request:

{user_request}
"""

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=PLANNER_MAX_TOKENS
        )
        return response.choices[0].message.content.strip()

    except Exception as exc:
        raise RuntimeError("Planner model unavailable") from exc


def plan_workflow(user_request: str, feature: str = "student-1") -> Dict[str, Any]:
    try:
        plan = call_model(user_request, feature)
    except RuntimeError:
        return {"status": "error", "agent": "planner_agent", "model": OLLAMA_MODEL,
                "feature": feature, "plan": "", "error": "Planner model unavailable"}
    return {
        "status": "completed",
        "agent": "planner_agent",
        "model": OLLAMA_MODEL,
        "objective": user_request,
        "feature": feature,
        "plan": plan,
        "steps": default_steps(),
        "human_approval_required": True
    }


if __name__ == "__main__":
    import json

    result = plan_workflow("Summarise customer feedback for product 103.")
    print(json.dumps(result, indent=2))
