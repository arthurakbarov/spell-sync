#!/usr/bin/env python3
"""Stdlib dead-code audit producing a review report."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".artifacts" / "quality" / "dead-code-report.json"
SCAN_ROOTS = (ROOT / "scripts", ROOT / "spell_sync")


def _defined_symbols(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def main() -> int:
    candidates: list[dict[str, str]] = []
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel.endswith("__init__.py"):
                continue
            if path.stat().st_size >= 80:
                continue
            module = rel.replace("/", ".").removesuffix(".py")
            referenced = False
            for other in SCAN_ROOTS:
                if not other.is_dir():
                    continue
                for other_path in other.rglob("*.py"):
                    if other_path == path or "__pycache__" in other_path.parts:
                        continue
                    other_text = other_path.read_text(encoding="utf-8", errors="ignore")
                    if f"import {path.stem}" in other_text or module in other_text:
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
        "candidates": candidates[:50],
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = "success" if len(candidates) == 0 else "review-required"
    print(f"DEAD_CODE_AUDIT_RESULT={result}")
    print(f"DEAD_CODE_REPORT={REPORT}")
    return 0 if result == "success" else 0


if __name__ == "__main__":
    raise SystemExit(main())
