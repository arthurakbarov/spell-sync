"""Local documentation links resolve."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)]+)\)")


def test_getting_started_links_exist() -> None:
    for path in (ROOT / "README.md", ROOT / "docs/GETTING_STARTED.md"):
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1).split("#", 1)[0]
            if target.startswith("http"):
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), f"missing link target {target} from {path.name}"
