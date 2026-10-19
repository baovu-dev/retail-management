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
    timeout=OLLAMA_TIMEOUT_SECONDS
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
    prompt = f"""
{load_prompt()}

Feature:

{feature}

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
        return (
            "Objective: Process the user request.\n"
            "Steps: Plan, work, review, human decision.\n"
            "Evidence Required: Feature records from the database API.\n"
            "Human Approval: Required.\n"
            f"Fallback Reason: {exc}"
        )


def plan_workflow(user_request: str, feature: str = "student-1") -> Dict[str, Any]:
    return {
        "status": "completed",
        "agent": "planner_agent",
        "model": OLLAMA_MODEL,
        "objective": user_request,
        "feature": feature,
        "plan": call_model(user_request, feature),
        "steps": default_steps(),
        "human_approval_required": True
    }


if __name__ == "__main__":
    import json

    result = plan_workflow("Summarise customer feedback for product 103.")
    print(json.dumps(result, indent=2))