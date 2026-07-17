#!/bin/sh
# Local CI — same checks as .github/workflows/test.yml
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if command -v python3.11 >/dev/null 2>&1; then
  PYTHON=python3.11
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
else
  PYTHON=python3
fi
pyver="$($PYTHON -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$pyver" in
  3.11|3.12|3.13) ;;
  *)
    echo "spell-sync CI requires Python 3.11+ (found $pyver via $PYTHON)" >&2
    exit 1
    ;;
esac

$PYTHON -m pip install -q ruff mypy pytest pytest-cov build wheel twine 'setuptools>=77'
$PYTHON -m pip install -q -e .
bash scripts/check-docs-style.sh
$PYTHON -m ruff check spell_sync tests
$PYTHON -m ruff format --check spell_sync tests
$PYTHON -m mypy spell_sync
$PYTHON -m pytest tests/ -q \
  --cov=spell_sync \
  --cov-branch \
  --cov-report=term-missing:skip-covered \
  --cov-report=json \
  --cov-fail-under=98
$PYTHON - <<'PY'
import json

totals = json.load(open("coverage.json", encoding="utf-8"))["totals"]
if totals["missing_lines"]:
    raise SystemExit(f"line coverage must be 100% ({totals['missing_lines']} lines missing)")
branches = totals["num_branches"]
branch_rate = 100.0 if not branches else 100.0 * totals["covered_branches"] / branches
if branch_rate < 96:
    raise SystemExit(f"branch coverage must be at least 96% ({branch_rate:.2f}%)")
print(f"coverage policy: 100% lines, {branch_rate:.2f}% branches")
PY
rm -f coverage.json
rm -rf build dist spell_sync.egg-info
$PYTHON -m build -w -n
$PYTHON -m twine check dist/*
wheel="$(ls dist/*.whl | head -1)"
smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/spell-sync-wheel.XXXXXX")"
$PYTHON -m venv "$smoke_dir/venv"
venv_python="$smoke_dir/venv/bin/python"
if [ ! -x "$venv_python" ]; then
  venv_python="$smoke_dir/venv/Scripts/python.exe"
fi
"$venv_python" -m pip install -q "$wheel"
"$venv_python" -m spell_sync version >/dev/null
"$venv_python" -m spell_sync --help >/dev/null
rm -rf "$smoke_dir" dist
if [ ! -f wordlist.txt ]; then
  $PYTHON -m spell_sync init
fi
$PYTHON -m spell_sync lint --strict
$PYTHON -m pytest tests/test_gui_smoke.py -q
