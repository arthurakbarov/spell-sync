#!/usr/bin/env python3
"""Read-only agent context rollup (branch, dirty, necessity, suggested runner)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_ci_necessity import assess_ci_necessity  # noqa: E402

_RULES = (
    ".cursor/rules/project-development.mdc",
    ".cursor/rules/agent-workflow.mdc",
    ".cursor/rules/after-changes.mdc",
    ".cursor/rules/git-change-management.mdc",
    ".cursor/rules/project-safety.mdc",
)
_SKILLS = (
    ".cursor/skills/project-development/SKILL.md",
    ".cursor/skills/repository-workflow/SKILL.md",
    ".cursor/skills/select-and-run-tests/SKILL.md",
    ".cursor/skills/security-audit/SKILL.md",
    ".cursor/skills/autonomous-work/SKILL.md",
    ".cursor/skills/preflight-publish/SKILL.md",
)
_DOCS = (
    "AGENTS.md",
    "docs/AGENT_DEVELOPMENT.md",
    "docs/ENGINEERING_COMPLETION.md",
    "docs/TESTING_STRATEGY.md",
    "docs/CONTRACTS.md",
    "docs/FEATURE_MATRIX.md",
    ".cursor/README.md",
)

_SUGGESTED = {
    "no-action": "none",
    "commit-gate-sufficient": "python3 scripts/run_dev_loop.py --commit-gate",
    "lightweight-sufficient": "python3 scripts/run_lightweight_validation.py",
    "full-required": "scripts/ci.sh",
}

_SIBLING_NAMES = ("spell-words", "spell-sync-dev")


def _git_at(root: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _count_lines(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def _is_git_repo(path: Path) -> bool:
    return bool(_git_at(path, ["rev-parse", "--git-dir"]))


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    home = Path.home().resolve()
    try:
        return "$HOME/" + resolved.relative_to(home).as_posix()
    except ValueError:
        return resolved.name


def _repo_snapshot(root: Path) -> dict[str, object]:
    branch = _git_at(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    head = _git_at(root, ["rev-parse", "HEAD"]) or "unknown"
    head_short = head[:12] if len(head) >= 12 else head
    staged = _count_lines(_git_at(root, ["diff", "--cached", "--name-only"]))
    unstaged = _count_lines(_git_at(root, ["diff", "--name-only"]))
    untracked = _count_lines(_git_at(root, ["ls-files", "--others", "--exclude-standard"]))
    dirty = staged + unstaged + untracked > 0
    return {
        "name": root.name,
        "displayPath": _display_path(root),
        "branch": branch,
        "head": head,
        "headShort": head_short,
        "dirty": dirty,
        "stagedCount": staged,
        "unstagedCount": unstaged,
        "untrackedCount": untracked,
    }


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_sibling_roots() -> dict[str, Path]:
    """Best-effort paths for the maintainer three-repo workspace."""
    found: dict[str, Path] = {}
    words_env = _env_path("SPELL_WORDS")
    dev_env = _env_path("SPELL_SYNC_DEV")
    workspace = _env_path("SPELL_SYNC_WORKSPACE")

    if words_env is not None:
        found["spell-words"] = words_env
    if dev_env is not None:
        found["spell-sync-dev"] = dev_env

    if ROOT.name == "spell-sync" and ROOT.parent.name == "spell-words":
        found.setdefault("spell-words", ROOT.parent)
        found.setdefault("spell-sync-dev", ROOT.parent.parent / "spell-sync-dev")

    if workspace is not None:
        found.setdefault("spell-words", workspace / "spell-words")
        found.setdefault("spell-sync-dev", workspace / "spell-sync-dev")

    code_root = Path.home() / "code"
    found.setdefault("spell-words", code_root / "spell-words")
    found.setdefault("spell-sync-dev", code_root / "spell-sync-dev")

    present: dict[str, Path] = {}
    for name in _SIBLING_NAMES:
        path = found.get(name)
        if path is not None and path.is_dir() and _is_git_repo(path):
            present[name] = path.resolve()
    return present


def collect(*, purpose: str = "local") -> dict[str, object]:
    primary = _repo_snapshot(ROOT)
    necessity = assess_ci_necessity(ROOT, purpose=purpose, explain=False)
    suggested = _SUGGESTED.get(necessity.result, "python3 scripts/run_dev_loop.py")
    if primary["dirty"] and necessity.result in {"no-action", "commit-gate-sufficient"}:
        edit_loop = "python3 scripts/run_dev_loop.py"
    else:
        edit_loop = suggested if necessity.result != "no-action" else "none"

    siblings = [_repo_snapshot(path) for path in resolve_sibling_roots().values()]
    siblings.sort(key=lambda item: str(item["name"]))

    return {
        "repository": primary["name"],
        "branch": primary["branch"],
        "head": primary["head"],
        "headShort": primary["headShort"],
        "dirty": primary["dirty"],
        "stagedCount": primary["stagedCount"],
        "unstagedCount": primary["unstagedCount"],
        "untrackedCount": primary["untrackedCount"],
        "necessityPurpose": purpose,
        "necessityResult": necessity.result,
        "necessityReason": necessity.reason,
        "suggestedEditLoop": edit_loop,
        "suggestedCheckpoint": _SUGGESTED["commit-gate-sufficient"],
        "suggestedFullGate": _SUGGESTED["full-required"],
        "workspaceRepos": siblings,
        "rules": list(_RULES),
        "skills": list(_SKILLS),
        "docs": list(_DOCS),
    }


def _print_text(payload: dict[str, object]) -> None:
    print(f"AGENT_CONTEXT_REPOSITORY={payload['repository']}")
    print(f"AGENT_CONTEXT_BRANCH={payload['branch']}")
    print(f"AGENT_CONTEXT_HEAD={payload['headShort']}")
    print(f"AGENT_CONTEXT_DIRTY={'true' if payload['dirty'] else 'false'}")
    print(f"AGENT_CONTEXT_STAGED={payload['stagedCount']}")
    print(f"AGENT_CONTEXT_UNSTAGED={payload['unstagedCount']}")
    print(f"AGENT_CONTEXT_UNTRACKED={payload['untrackedCount']}")
    print(f"AGENT_CONTEXT_NECESSITY={payload['necessityResult']}")
    print(f"AGENT_CONTEXT_NECESSITY_REASON={payload['necessityReason']}")
    print(f"AGENT_CONTEXT_SUGGESTED_EDIT={payload['suggestedEditLoop']}")
    print(f"AGENT_CONTEXT_SUGGESTED_CHECKPOINT={payload['suggestedCheckpoint']}")
    print(f"AGENT_CONTEXT_SUGGESTED_FULL_GATE={payload['suggestedFullGate']}")
    siblings = payload.get("workspaceRepos", [])
    assert isinstance(siblings, list)
    print(f"AGENT_CONTEXT_WORKSPACE_REPO_COUNT={len(siblings)}")
    for item in siblings:
        assert isinstance(item, dict)
        dirty = "true" if item["dirty"] else "false"
        print(
            "AGENT_CONTEXT_WORKSPACE_REPO="
            f"{item['name']} branch={item['branch']} "
            f"head={item['headShort']} dirty={dirty}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument(
        "--purpose",
        choices=("local", "publish"),
        default="local",
        help="CI necessity purpose (default: local)",
    )
    args = parser.parse_args(argv)
    payload = collect(purpose=args.purpose)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
