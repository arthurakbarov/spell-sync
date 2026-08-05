#!/usr/bin/env python3
"""Publish preflight: clean tree + necessity, optionally full CI + evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_ci_necessity import assess_ci_necessity  # noqa: E402
from scripts.cli_text import format_field_block, format_kv_lines  # noqa: E402


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _tree_dirty() -> bool:
    staged = _git(["diff", "--cached", "--name-only"]).stdout.strip()
    unstaged = _git(["diff", "--name-only"]).stdout.strip()
    untracked = _git(["ls-files", "--others", "--exclude-standard"]).stdout.strip()
    return bool(staged or unstaged or untracked)


def _run(argv: list[str]) -> int:
    print(f"PREFLIGHT_COMMAND={' '.join(argv)}", flush=True)
    proc = subprocess.run(argv, cwd=ROOT, check=False)
    print(f"PREFLIGHT_EXIT={proc.returncode}", flush=True)
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run full CI and evidence after clean-tree and necessity checks.",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Pass --release to check_ci_evidence.py (tag/publish workflows).",
    )
    args = parser.parse_args(argv)

    print("PREFLIGHT_STAGE=clean-tree", flush=True)
    if _tree_dirty():
        print(
            format_kv_lines(
                [
                    ("PREFLIGHT_RESULT", "blocked"),
                    ("PREFLIGHT_REASON", "dirty-working-tree"),
                ]
            ),
            flush=True,
        )
        return 2

    print("PREFLIGHT_STAGE=necessity", flush=True)
    necessity = assess_ci_necessity(ROOT, purpose="publish", explain=True)
    print(
        format_field_block(
            [
                ("necessity", str(necessity.result)),
                ("reason", str(necessity.reason)),
            ]
        ),
        flush=True,
    )
    print(f"PREFLIGHT_NECESSITY={necessity.result}", flush=True)
    print(f"PREFLIGHT_NECESSITY_REASON={necessity.reason}", flush=True)

    print("PREFLIGHT_STAGE=privacy", flush=True)
    code = _run([sys.executable, str(ROOT / "scripts" / "scan_privacy_tree.py")])
    if code != 0:
        print("PREFLIGHT_RESULT=failed", flush=True)
        print("PREFLIGHT_REASON=privacy", flush=True)
        return code
    print("PREFLIGHT_PRIVACY=success", flush=True)

    if not args.execute:
        print(
            format_field_block(
                [
                    ("next", "scripts/ci.sh"),
                    ("next", "python3 scripts/check_ci_evidence.py"),
                    ("next", "privacy-export skill checklist"),
                ]
            ),
            flush=True,
        )
        print("PREFLIGHT_RESULT=ready-plan", flush=True)
        print("PREFLIGHT_NEXT=scripts/ci.sh", flush=True)
        print("PREFLIGHT_NEXT=python3 scripts/check_ci_evidence.py", flush=True)
        print("PREFLIGHT_NEXT=privacy-export skill checklist", flush=True)
        print("PREFLIGHT_HINT=re-run with --execute to run CI+evidence", flush=True)
        return 0

    print("PREFLIGHT_STAGE=full-ci", flush=True)
    code = _run(["bash", str(ROOT / "scripts" / "ci.sh")])
    if code != 0:
        print("PREFLIGHT_RESULT=failed", flush=True)
        print("PREFLIGHT_REASON=ci", flush=True)
        return code

    evidence_cmd = [sys.executable, str(ROOT / "scripts" / "check_ci_evidence.py")]
    if args.release:
        evidence_cmd.append("--release")
    print("PREFLIGHT_STAGE=evidence", flush=True)
    code = _run(evidence_cmd)
    if code != 0:
        print("PREFLIGHT_RESULT=failed", flush=True)
        print("PREFLIGHT_REASON=evidence", flush=True)
        return code

    print("PREFLIGHT_RESULT=success", flush=True)
    print("PREFLIGHT_REMOTE=not-performed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
