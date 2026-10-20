"""Local Python 3.11 CI + isolated three-service test of the default Dockerfile.

No original DB mounts, ports, keys, AI services or initializers. Existing RUN and
its validation stack are untouched. New image test data remain in RUN/image-data.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(os.environ["ORDERS_VALIDATION_RUN"]).resolve()
IMAGE = "student4-orders:release1-local"
os.umask(0o077)
if RUN == ROOT or ROOT in RUN.parents:
    raise SystemExit("RUN must be outside the repository")


def command(args, log):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    (RUN / log).write_text(result.stdout + result.stderr)
    print(log, "exit", result.returncode, flush=True)
    result.check_returncode()
    return result.stdout


parser = argparse.ArgumentParser()
parser.add_argument("--build", action="store_true", help="Build the default Dockerfile; omit to use an already built image")
args = parser.parse_args()
if args.build:
    command(["docker", "build", "-t", IMAGE, "student-4"], "default-image-build.log")
image_id = command(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], "image-id.txt").strip()
command(["docker", "run", "--rm", "--network", "none", IMAGE, "python", "-c",
         "from pathlib import Path; import sys; assert not list(Path('/app').rglob('*.db')); print(sys.version); print('No DB embedded in image')"], "image-contents.log")

# Repository bind is read-only. pytest's SQLite fixtures and bytecode/cache stay off it.
command(["docker", "run", "--rm", "-v", str(ROOT) + ":/repo:ro", "-w", "/repo/student-4",
         "-e", "AI_ENABLED=false", "-e", "MCP_ENABLED=false", "-e", "RAG_ENABLED=false",
         "-e", "PYTHONDONTWRITEBYTECODE=1", IMAGE, "sh", "-c",
         "python -m pip install -r tests/requirements.txt && python -m pip check && python -m pytest tests/ -v -p no:cacheprovider"], "ci-python311.log")
for file in ["docker-compose.yml", "student-4/docker-compose.yml"]:
    command(["docker", "compose", "-f", file, "config", "--quiet"], "compose-" + file.replace("/", "-") + ".log")

(RUN / "image-data").mkdir(exist_ok=True)
script = str(ROOT / "scripts/orders/image_check.py") + ":/validation/image_check.py:ro"
compose = {"name": "orders-image-validation", "services": {
    "database": {"image": IMAGE, "command": ["python", "/validation/image_check.py", "serve-db"],
                 "volumes": [script, str(RUN / "image-data") + ":/validation-data"]},
    "backend": {"image": IMAGE, "command": ["python", "backend/app.py"],
                "environment": {"DATABASE_URL": "http://database:6004", "AI_ENABLED": "false", "MCP_ENABLED": "false", "RAG_ENABLED": "false"},
                "volumes": [script]},
    "frontend": {"image": IMAGE, "command": ["python", "frontend/app.py"],
                 "environment": {"API_BASE": "http://localhost:5004", "SHARED_BASE": "http://localhost:5000"}}
}, "networks": {"default": {"internal": True}}}
path = RUN / "image-compose.json"
path.write_text(json.dumps(compose, indent=2))
prefix = ["docker", "compose", "-f", str(path)]
try:
    command(prefix + ["up", "-d", "--no-build"], "image-up.log")
    output = command(prefix + ["exec", "-T", "backend", "python", "/validation/image_check.py", "check"], "image-integration.json")
    rows = json.loads(output)
    print("Built-image integration:", sum(r["result"] == "PASS" for r in rows), "PASS", flush=True)
    (RUN / "local-ci-result.json").write_text(json.dumps({"image": IMAGE, "image_id": image_id,
        "python_ci": "passed", "compose": "passed", "image_integration": rows, "remote_ci": "not run"}, indent=2))
finally:
    # Only these three new containers/network are removed; bind-mounted test data stay.
    command(prefix + ["down"], "image-down.log")
