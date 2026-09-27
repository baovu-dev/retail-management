import argparse
from datetime import datetime

from modes import ai_mode

MODES = {
    "ai-mode": ai_mode.run,
}


def stage(name, message):
    time = datetime.now().strftime("%H:%M:%S")
    print(f"[{time}] {name:<8} {message}")


def main():
    parser = argparse.ArgumentParser(description="KICKLAB shared agentic loop")
    parser.add_argument("--mode", required=True, choices=MODES.keys())
    args = parser.parse_args()

    print(f"=== KICKLAB agentic loop: {args.mode} ===")
    passed = MODES[args.mode](stage)
    print(f"=== Result: {'PASS' if passed else 'FAIL'} ===")


if __name__ == "__main__":
    main()