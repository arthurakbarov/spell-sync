#!/usr/bin/env python3
"""Opt-in installer for spell-sync commit-msg hooks (maintainer clones).

Installs a commit-msg hook that runs scripts/validate_commit_messages.py against
the staged message. Does not touch product wordlist-repo hooks (doctor
install-hooks). Refuses to clobber unmanaged hooks without --force.
"""

from __future__ import annotations

import argparse
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_NAME = "commit-msg"
MARKER = "# spell-sync-commit-msg-hook"


def _hook_body(spell_sync_root: Path) -> str:
    validator = (spell_sync_root / "scripts" / "validate_commit_messages.py").resolve()
    return f"""#!/usr/bin/env bash
{MARKER}
# Validates the commit subject/body shape for spell-sync / shared nix policy.
set -euo pipefail
MSG_FILE=${{1:-}}
if [[ -z "$MSG_FILE" || ! -f "$MSG_FILE" ]]; then
  echo "spell-sync commit-msg: missing message file" >&2
  exit 1
fi
python3 {validator.as_posix()} --message-file "$MSG_FILE"
"""


def _git_dir(repo: Path) -> Path | None:
    git = repo / ".git"
    if git.is_dir():
        return git
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            return (repo / text.split(":", 1)[1].strip()).resolve()
    return None


def install(*, repo: Path, force: bool = False) -> int:
    git_dir = _git_dir(repo)
    if git_dir is None:
        print("HOOKS_RESULT=failed")
        print("HOOKS_REASON=not-a-git-repo")
        return 1
    hooks = git_dir / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    path = hooks / HOOK_NAME
    body = _hook_body(ROOT)
    if path.is_file() and MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        if not force:
            print("HOOKS_RESULT=failed")
            print("HOOKS_REASON=unmanaged-hook-present")
            print(f"HOOKS_PATH={path}")
            print("HOOKS_HINT=re-run with --force to replace")
            return 2
    path.write_text(body, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("HOOKS_RESULT=success")
    print(f"HOOKS_INSTALLED={HOOK_NAME}")
    print(f"HOOKS_REPO={repo}")
    return 0


def remove(*, repo: Path) -> int:
    git_dir = _git_dir(repo)
    if git_dir is None:
        print("HOOKS_RESULT=failed")
        print("HOOKS_REASON=not-a-git-repo")
        return 1
    path = git_dir / "hooks" / HOOK_NAME
    if not path.is_file():
        print("HOOKS_RESULT=success")
        print("HOOKS_REMOVED=none")
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    if MARKER not in text:
        print("HOOKS_RESULT=failed")
        print("HOOKS_REASON=unmanaged-hook-present")
        return 2
    path.unlink()
    print("HOOKS_RESULT=success")
    print(f"HOOKS_REMOVED={HOOK_NAME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("install", "remove", "status"),
        help="install, remove, or status",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Git repository to modify (default: this spell-sync checkout)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an unmanaged commit-msg hook",
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.action == "install":
        return install(repo=repo, force=args.force)
    if args.action == "remove":
        return remove(repo=repo)
    git_dir = _git_dir(repo)
    if git_dir is None:
        print("HOOKS_RESULT=failed")
        print("HOOKS_REASON=not-a-git-repo")
        return 1
    path = git_dir / "hooks" / HOOK_NAME
    if not path.is_file():
        print("HOOKS_RESULT=success")
        print("HOOKS_STATUS=missing")
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    managed = MARKER in text
    print("HOOKS_RESULT=success")
    print(f"HOOKS_STATUS={'managed' if managed else 'unmanaged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
