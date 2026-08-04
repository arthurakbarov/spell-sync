#!/usr/bin/env bash
# Optional helper: turn a Spell Sync personal workspace into a private GitHub repo.
# Does not run Spell Sync. Requires: git, gh (authenticated).
set -euo pipefail

usage() {
  echo "Usage: $0 <path-to-personal-workspace-folder>" >&2
  echo "Example: $0 \"\$HOME/Documents/Spell Sync\"" >&2
  exit 2
}

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

ROOT="$(cd -- "$1" && pwd)"
WORDLIST="$ROOT/wordlist.txt"
CONFIG="$ROOT/spell-sync.toml"

if [[ ! -f "$WORDLIST" ]]; then
  echo "error: missing wordlist.txt in $ROOT" >&2
  echo "Create the Spell Sync project first (TUI Start here, or: spell-sync init)." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "error: git not found" >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh not found (install GitHub CLI and run: gh auth login)" >&2
  exit 1
fi

cd "$ROOT"

if [[ ! -d .git ]]; then
  git init
fi

git add wordlist.txt
if [[ -f "$CONFIG" ]]; then
  git add spell-sync.toml
fi
if [[ -f .gitignore ]]; then
  git add .gitignore
fi

if git diff --cached --quiet; then
  echo "nothing new to commit (working tree already staged/clean)"
else
  git commit -m "Add personal Spell Sync word list"
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "remote 'origin' already exists; pushing…"
  git push -u origin HEAD
else
  # Private by default — do not use --public.
  gh repo create spell-sync-words --private --source=. --remote=origin --push
fi

echo "Done. On another machine: gh repo clone <you>/spell-sync-words <folder>"
echo "Then open that folder's wordlist.txt in Spell Sync."
