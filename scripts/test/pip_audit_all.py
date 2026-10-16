"""Run pip-audit against every requirements file tracked in the repo.

pre-commit runs hooks in an isolated environment, so a plain `pip-audit`
would only audit that environment. This checks the project's real
dependencies instead.
"""
import subprocess
import sys
from pathlib import Path


IGNORE_FILE = Path(__file__).with_name("pip-audit-ignore.txt")


def ignored_ids():
    """Vulnerability IDs reviewed and accepted, with reasons in the ignore file."""
    if not IGNORE_FILE.exists():
        return []
    ids = []
    for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            ids.append(entry)
    return ids


def tracked_requirements():
    result = subprocess.run(
        ["git", "ls-files", "*requirements*.txt"],
        capture_output=True, text=True, check=True,
    )
    return [path for path in result.stdout.splitlines() if path.strip()]


def main():
    # Files passed by pre-commit (the ones in this commit), or every tracked file if run directly
    files = sys.argv[1:] or tracked_requirements()    #files = tracked_requirements()
    if not files:
        print("No requirements files found.")
        return 0

    failed = []
    for path in files:
        print(f"\n=== pip-audit: {path} ===", flush=True)
        command = [sys.executable, "-m", "pip_audit", "-r", path, "--progress-spinner", "off"]
        for vuln_id in ignored_ids():
            command += ["--ignore-vuln", vuln_id]
        result = subprocess.run(command)
        if result.returncode != 0:
            failed.append(path)

    if failed:
        print("\nVulnerabilities or audit errors in: " + ", ".join(failed))
        return 1
    print(f"\nAll {len(files)} requirements files passed pip-audit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())