#!/bin/sh
# Local CI entry point (agent-first, machine-readable summary).
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
if command -v python3.11 >/dev/null 2>&1; then
  exec python3.11 "$root/scripts/ci_runner.py" "$@"
elif command -v python3.12 >/dev/null 2>&1; then
  exec python3.12 "$root/scripts/ci_runner.py" "$@"
else
  exec python3 "$root/scripts/ci_runner.py" "$@"
fi
