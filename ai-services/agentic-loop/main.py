import argparse
from datetime import datetime
from pathlib import Path

from modes import ai_mode, mcp_mode, rag_mode

MODES = {
    "ai-mode": ai_mode.run,
    "mcp": mcp_mode.run,
    "rag": rag_mode.run,
}

LOG = []

def emit(line):
    print(line)
    LOG.append(line)

def stage(name, message):
    time = datetime.now().strftime("%H:%M:%S")
    emit(f"[{time}] {name:<8} {message}")

def main():
    parser = argparse.ArgumentParser(description="KICKLAB shared agentic loop")
    parser.add_argument("--mode", required=True, choices=MODES.keys())
    args = parser.parse_args()

    emit(f"=== KICKLAB agentic loop: {args.mode} ===")
    passed = MODES[args.mode](stage)
    emit(f"=== Result: {'PASS' if passed else 'FAIL'} ===")

    out = Path(__file__).parent / "outputs" / f"{args.mode}-{datetime.now():%Y%m%d-%H%M%S}.txt"
    out.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(f"Saved output to {out}")

if __name__ == "__main__":
    main()