#!/usr/bin/env python3
"""Validate user-facing documentation contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
GETTING_STARTED = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")


def main() -> int:
    checks = [
        ("problem-statement", "underlined again" in README or "marked as misspelled" in README),
        ("pull-direction", "Collect words" in README and "Pull" in README),
        ("push-direction", "Update apps" in README and "Push" in README),
        ("removal-warning", "may remove" in README.lower()),
        ("builtin-guarantee", "Built-in dictionaries" in README),
        ("getting-started-linked", "GETTING_STARTED.md" in README),
        ("git-optional", "Git is optional" in README or "Git is **optional**" in README),
        ("no-spell-sync-dev-required", "spell-sync-dev" not in README),
        ("getting-started-exists", GETTING_STARTED.startswith("# Getting Started")),
        (
            "private-git-optional",
            "private" in GETTING_STARTED.lower() and "optional" in GETTING_STARTED.lower(),
        ),
        ("readme-cli-support-report", "support-report" in README),
        (
            "getting-started-recovery-link",
            "RECOVERY.md" in GETTING_STARTED,
        ),
        (
            "getting-started-troubleshooting-link",
            "TROUBLESHOOTING.md" in GETTING_STARTED,
        ),
    ]
    for check_id, ok in checks:
        if not ok:
            print("USER_DOCUMENTATION_VALIDATION=failed")
            print(f"USER_DOCUMENTATION_FAILED_ID={check_id}")
            return 1
    print("USER_DOCUMENTATION_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
