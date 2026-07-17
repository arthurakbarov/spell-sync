#!/bin/sh
# Minimal markdown style gates for committed docs.
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

fail=0

hr="$(git grep -n '^---$' -- '*.md' docs 2>/dev/null || true)"
if [ -n "$hr" ]; then
  echo "Horizontal rules (---) are forbidden in committed .md files:" >&2
  echo "$hr" >&2
  fail=1
fi

html="$(git grep -n '<!--' -- '*.md' docs 2>/dev/null | grep -v 'No HTML comments' || true)"
if [ -n "$html" ]; then
  echo "HTML comments are forbidden in committed .md files:" >&2
  echo "$html" >&2
  fail=1
fi

if grep -q 'requires-python = ">=3\\.[0-9]"' pyproject.toml 2>/dev/null; then
  echo "requires-python must be >=3.11." >&2
  fail=1
fi

for doc in docs/DEVELOPMENT.md docs/CONTRIBUTING.md; do
  if [ -f "$doc" ] && ! grep -q '3\.11+' "$doc"; then
    echo "Expected Python 3.11+ in $doc." >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "Docs style OK."
