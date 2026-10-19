import argparse
import json

from coordinator import ALLOWED_DECISIONS, record_decision, run_workflow


def ask_decision() -> str:
    print("\nDecision options:")
    for number, option in enumerate(ALLOWED_DECISIONS, start=1):
        print(f"  {number} - {option}")
    while True:
        choice = input("Choose 1-4: ").strip()
        if choice in {"1", "2", "3", "4"}:
            return ALLOWED_DECISIONS[int(choice) - 1]
        print("Please enter 1, 2, 3 or 4.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a KICKLAB multi-agent workflow from the terminal")
    parser.add_argument("--request", default="Summarise customer feedback for product 103.")
    parser.add_argument("--feature", default="student-1")
    args = parser.parse_args()

    print(f"Running workflow for {args.feature}: {args.request}\n")
    result = run_workflow(args.request, args.feature)

    print(f"Workflow ID: {result['workflow_id']}  ({result['duration_ms']} ms)\n")
    print("=== PLANNER ===")
    print(result["planner_result"]["plan"])
    print(f"\n=== WORKER ({result['worker_result'].get('evidence_count', 0)} evidence records) ===")
    print(result["worker_result"]["output"])
    print("\n=== REVIEWER ===")
    print(result["reviewer_result"]["review"])

    print("\n=== HUMAN REVIEW ===")
    decision = ask_decision()
    reviewer = input("Your name: ").strip()
    comment = input("Reason for your decision: ").strip()
    corrected_output = None
    if decision == "Correct":
        corrected_output = input("Corrected output: ").strip()

    outcome = record_decision(result["workflow_id"], decision, reviewer, comment, corrected_output)
    print("\n=== DECISION RECORDED ===")
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    main()