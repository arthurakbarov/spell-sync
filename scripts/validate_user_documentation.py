#!/usr/bin/env python3
"""Validate user-facing documentation contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
GETTING_STARTED = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
TROUBLESHOOTING = (ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
SUPPORTED_ENVIRONMENTS = (ROOT / "docs" / "SUPPORTED_ENVIRONMENTS.md").read_text(encoding="utf-8")


def main() -> int:
    checks = [
        ("problem-statement", "underlined again" in README or "marked as misspelled" in README),
        ("pull-direction", "Collect my words" in README and "Pull" in README),
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
        (
            "getting-started-cli-bridge",
            "spell-sync pull" in GETTING_STARTED
            and "spell-sync init" in GETTING_STARTED
            and "doctor" in GETTING_STARTED,
        ),
        (
            "getting-started-beginner-path",
            "The problem" in GETTING_STARTED
            and "Start here" in GETTING_STARTED
            and "Review and update" in GETTING_STARTED
            and "Fastest path" in GETTING_STARTED,
        ),
        (
            "readme-beginner-pointer",
            "Getting Started" in README and "Start here" in README,
        ),
        (
            "troubleshooting-config-check",
            "config-check" in TROUBLESHOOTING,
        ),
        (
            "readme-support-report-output",
            "support-report --output" in README,
        ),
        (
            "troubleshooting-status",
            "spell-sync status" in TROUBLESHOOTING,
        ),
        (
            "troubleshooting-lint",
            "spell-sync lint" in TROUBLESHOOTING,
        ),
        (
            "supported-environments-windows-honesty",
            "capability-limited" in SUPPORTED_ENVIRONMENTS,
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
