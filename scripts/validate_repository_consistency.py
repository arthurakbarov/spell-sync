#!/usr/bin/env python3
"""Validate cross-surface repository consistency."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures: list[str] = []
    if "spell-sync-dev" in readme:
        failures.append("[CONSISTENCY-PRIVATE-REFERENCE-007] README references spell-sync-dev")
    if "/Users/" in readme:
        failures.append("[CONSISTENCY-PRIVATE-REFERENCE-007] README contains owner path")
    for doc in ("docs/GETTING_STARTED.md", "docs/PERSONAL_WORKSPACE.md", "docs/SUPPORTED_APPS.md"):
        if not (ROOT / doc).is_file():
            failures.append(f"[CONSISTENCY-DOC-FILE-002] missing {doc}")
    dashboard = (ROOT / "spell_sync/tui/screens/dashboard.py").read_text(encoding="utf-8")
    if "COLLECT_WORDS_TECHNICAL" not in dashboard:
        failures.append("[CONSISTENCY-TUI-ACTION-003] dashboard missing collect label")
    if "UPDATE_APPS_TECHNICAL" not in dashboard:
        failures.append("[CONSISTENCY-TUI-ACTION-003] dashboard missing update label")
    if not re.search(r"spell-sync(\s|$)", readme):
        failures.append("[CONSISTENCY-DOC-COMMAND-001] README missing spell-sync command")
    if failures:
        print("REPOSITORY_CONSISTENCY_RESULT=failed")
        for item in failures:
            print(item)
        return 1
    print("REPOSITORY_CONSISTENCY_RESULT=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
