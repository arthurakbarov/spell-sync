#!/usr/bin/env python3
"""Validate spell-sync / nix-shared commit message shape on recent history."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONVENTIONAL_PREFIX = re.compile(
    r"^(feat|fix|docs|chore|refactor|test|ci|build|style|perf)(\(.+\))?:\s+",
    re.I,
)
WAVE_PHASE_PREFIX = re.compile(r"^(Wave|Phase)\s+[A-Za-z0-9._-]+\s*:\s*", re.I)
HYGIENE_SUBJECT = re.compile(
    r"^(Format |Fix ruff|Remove unused|Address ruff|Apply ruff|Ruff |Lint |"
    r"Fix formatting|Silence |Drop unused|Satisfy ruff)",
    re.I,
)


@dataclass(frozen=True)
class CommitMessage:
    sha: str
    subject: str
    body: str


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
    )


def load_commits(repo: Path, limit: int) -> list[CommitMessage]:
    raw = _git(repo, "log", f"-n{limit}", "--format=%H%x1f%s%x1f%b%x1e")
    commits: list[CommitMessage] = []
    for entry in raw.split("\x1e"):
        entry = entry.strip("\n")
        if not entry.strip():
            continue
        parts = entry.split("\x1f", 2)
        sha = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        body = parts[2] if len(parts) > 2 else ""
        commits.append(CommitMessage(sha=sha, subject=subject, body=body))
    return commits


def validate_message(commit: CommitMessage, *, check_hygiene: bool) -> list[str]:
    errors: list[str] = []
    subject = commit.subject.strip()
    short = commit.sha[:8]
    if not subject:
        errors.append(f"{short}: empty subject")
        return errors
    if not subject.endswith("."):
        errors.append(f"{short}: subject must end with '.' ({subject!r})")
    if CONVENTIONAL_PREFIX.match(subject):
        errors.append(f"{short}: Conventional Commit prefix forbidden ({subject!r})")
    if WAVE_PHASE_PREFIX.match(subject):
        errors.append(f"{short}: wave/phase subject prefix forbidden ({subject!r})")
    if subject[0].islower():
        errors.append(f"{short}: subject should start with a capital letter ({subject!r})")
    body = commit.body.strip("\n")
    if body.strip():
        # Reconstruct blank-line rule from subject + body fields.
        # git %b is body only; blank line is implied by having a body.
        pass
    if check_hygiene and HYGIENE_SUBJECT.match(subject):
        errors.append(
            f"{short}: hygiene follow-up should be folded into the producing commit ({subject!r})"
        )
    return errors


def validate_history(
    repo: Path,
    *,
    limit: int,
    check_hygiene: bool,
) -> list[str]:
    errors: list[str] = []
    for commit in load_commits(repo, limit):
        errors.extend(validate_message(commit, check_hygiene=check_hygiene))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Git repository root (default: spell-sync)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=40,
        help="Number of recent commits to validate (default: 40)",
    )
    parser.add_argument(
        "--check-hygiene",
        action="store_true",
        help="Fail on format/ruff/unused-import follow-up subjects",
    )
    args = parser.parse_args(argv)
    errors = validate_history(
        args.repo.resolve(),
        limit=max(1, args.limit),
        check_hygiene=args.check_hygiene,
    )
    if errors:
        print("COMMIT_MESSAGE_VALIDATE: fail")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"COMMIT_MESSAGE_VALIDATE: ok (checked {args.limit} commits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
