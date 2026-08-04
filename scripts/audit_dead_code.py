#!/usr/bin/env python3
"""Stdlib dead-code audit producing a review report."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".artifacts" / "quality" / "dead-code-report.json"
# Product modules only — scripts are often CLI entry points referenced outside imports.
SCAN_ROOTS = (ROOT / "spell_sync",)
REFERENCE_ROOTS = (ROOT / "scripts", ROOT / "spell_sync")
# Heuristic: tiny product modules. Raised above __main__.py (~238 B) so the scan is non-vacuous.
MAX_CANDIDATE_BYTES = 1024
ENTRY_MARKERS = ('if __name__ == "__main__"', "if __name__ == '__main__'")


def main() -> int:
    candidates: list[dict[str, str]] = []
    scanned_small = 0
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel.endswith("__init__.py") or rel.endswith("__main__.py"):
                continue
            size = path.stat().st_size
            if size >= MAX_CANDIDATE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in ENTRY_MARKERS):
                continue
            scanned_small += 1
            stem = path.stem
            module = rel.replace("/", ".").removesuffix(".py")
            import_markers = (
                f"import {stem}",
                f"from .{stem} ",
                f"from ..{stem} ",
                f"from ...{stem} ",
                f"from {module} ",
                f"import {module}",
                module,
            )
            referenced = False
            for other in REFERENCE_ROOTS:
                if not other.is_dir():
                    continue
                for other_path in other.rglob("*.py"):
                    if other_path == path or "__pycache__" in other_path.parts:
                        continue
                    other_text = other_path.read_text(encoding="utf-8", errors="ignore")
                    if any(marker in other_text for marker in import_markers):
                        referenced = True
                        break
                if referenced:
                    break
            if referenced:
                continue
            candidates.append(
                {
                    "path": rel,
                    "reason": "tiny-unreferenced-module",
                    "evidence": "no import references found by simple scan",
                }
            )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "candidateCount": len(candidates),
        "scannedSmallFileCount": scanned_small,
        "maxCandidateBytes": MAX_CANDIDATE_BYTES,
        "candidates": candidates[:50],
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = "success" if len(candidates) == 0 else "review-required"
    print(f"DEAD_CODE_AUDIT_RESULT={result}")
    print(f"DEAD_CODE_REPORT={REPORT}")
    print(f"DEAD_CODE_SCANNED_SMALL={scanned_small}")
    return 0 if result == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
