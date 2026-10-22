#!/usr/bin/env bash
# Run each student's endpoint tests separately; missing coverage blocks release.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPORT_DIR="${REPORT_DIR:-reports/cloud-validation}"
mkdir -p "$REPORT_DIR"
missing=0
for student in 1 2 3 4 5; do
  directory="student-$student/tests/post_commit"
  if [[ ! -d "$directory" ]] || ! find "$directory" -name 'test_*.py' -type f -print -quit | grep -q .; then
    echo "FAIL: student-$student has no post-commit endpoint tests" | tee -a "$REPORT_DIR/coverage.log"
    missing=1
  else
    echo "PRESENT: student-$student endpoint test files (execution still required)" | tee -a "$REPORT_DIR/coverage.log"
  fi
done
[[ "$missing" -eq 0 ]] || exit 1
[[ "${1:-}" != '--check-only' ]] || exit 0
# Per-student environments prevent backend module and dependency collisions.
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
status=0
for student in 1 2 3 4 5; do
  directory="student-$student"
  python -m venv "$work_dir/student-$student"
  interpreter="$work_dir/student-$student/bin/python"
  requirements=()
  if [[ -f "$directory/tests/requirements.txt" ]]; then
    requirements=(-r "$directory/tests/requirements.txt")
  else
    requirements=(-r "$directory/backend/requirements.txt")
  fi
  if ! "$interpreter" -m pip install "${requirements[@]}" pytest > "$REPORT_DIR/student-$student-install.log" 2>&1; then
    echo "FAIL: student-$student dependencies" | tee -a "$REPORT_DIR/coverage.log"
    status=1
    continue
  fi
  set +e
  PYTHONPATH="$PWD/$directory:$PWD/$directory/backend" AI_MODE_ENABLED=false AI_ENABLED=false MCP_ENABLED=false RAG_ENABLED=false MULTI_AGENT_ENABLED=false \
    "$interpreter" -m pytest "$directory/tests/post_commit" -v --junitxml="$REPORT_DIR/student-$student.xml" \
    2>&1 | tee "$REPORT_DIR/student-$student-tests.log"
  result=${PIPESTATUS[0]}
  set -e
  if [[ "$result" -ne 0 ]]; then status=1; fi
  # Empty, skipped or fewer than two executed tests cannot satisfy this gate.
  # Owners must also document which two distinct API functions their tests cover.
  if ! python - "$REPORT_DIR/student-$student.xml" <<'CHECK'
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
cases = root.findall('.//testcase')
valid = len(cases) >= 2 and all(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases)
sys.exit(0 if valid else 1)
CHECK
  then
    echo "FAIL: student-$student needs at least two passing, non-skipped endpoint tests" | tee -a "$REPORT_DIR/coverage.log"
    status=1
  fi
done
exit "$status"
