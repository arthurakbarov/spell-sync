#!/bin/sh
# Local CI entry point (agent-first, machine-readable summary).
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "CI requires PYTHON_BIN interpreter (default: python3); not found: $PYTHON_BIN" >&2
  exit 1
fi
exec "$PYTHON_BIN" "$root/scripts/ci_runner.py" "$@"
