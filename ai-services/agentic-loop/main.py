import argparse
from datetime import datetime
from pathlib import Path
import sys

from modes import ai_mode, mcp_mode, rag_mode

MODES = {
    "ai-mode": ai_mode.run,
    "mcp": mcp_mode.run,
    "rag": rag_mode.run,
}

LOG = []

def emit(line):
    print(line, flush=True)
    LOG.append(line)

def stage(name, message):
    time = datetime.now().strftime("%H:%M:%S")
    emit(f"[{time}] {name:<8} {message}")

def main():
    parser = argparse.ArgumentParser(description="KICKLAB shared agentic loop")
    parser.add_argument("--mode", required=True, choices=MODES.keys())
    parser.add_argument("--feature", choices=("student-1", "student-4"), default="student-1")
    parser.add_argument("--evidence-file", type=Path, help="Orders RAG: save a new actual run, or review a saved run")
    parser.add_argument("--review-file", type=Path, help="Orders RAG: source-grounded analyst review of the saved evidence")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "outputs")
    args = parser.parse_args()
    if args.feature == "student-4" and args.mode == "ai-mode":
        parser.error("Orders extends MCP/RAG only; existing AI validation uses student-1")
    if args.feature == "student-4" and args.mode == "rag" and not args.evidence_file:
        parser.error("Orders RAG requires --evidence-file")

    LOG.clear()
    emit(f"=== KICKLAB agentic loop: {args.mode} ===")
    if args.feature == "student-4":
        from modes import orders_mode
        try:
            passed = orders_mode.run(stage, args)
        except Exception as exc:
            # Never serialize auth request arguments, cookies or credential-bearing exceptions.
            stage("OBSERVE", f"FAIL: Orders validation interrupted ({type(exc).__name__})")
            passed = False
    else:
        passed = MODES[args.mode](stage)
    emit(f"=== Result: {'PASS' if passed else 'FAIL'} ===")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / f"{args.feature}-{args.mode}-{datetime.now():%Y%m%d-%H%M%S-%f}.txt"
    out.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(f"Saved output to {out}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
