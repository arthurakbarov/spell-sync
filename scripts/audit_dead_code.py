#!/usr/bin/env python3
"""Stdlib dead-code audit producing a review report.

Indexes every top-level product function via AST, then classifies each by where it
is referenced:

* ``fully-unreferenced`` — no reference in product code, config (``pyproject.toml``)
  or tests. This is unambiguous dead code and fails the audit.
* ``test-only`` — referenced only by the test suite. Reported for human review but
  not failed: a genuine dead helper kept alive by its tests looks identical to a
  legitimately public/util/test-support function that simply has thin product
  callers, and the two cannot be told apart mechanically.

Methods, classes, dataclasses, exceptions and Protocols are intentionally out of
scope: they are referenced through ``self``/inheritance/strings in ways a textual
scan cannot resolve without noise. Names re-exported through ``__all__`` are treated
as public API and never flagged.
"""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".artifacts" / "quality" / "dead-code-report.json"
PRODUCT_ROOT = ROOT / "spell_sync"
PRODUCT_REFERENCE_ROOTS = (ROOT / "spell_sync", ROOT / "scripts")
TEST_REFERENCE_ROOTS = (ROOT / "tests",)


def _py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _module_all_names(tree: ast.Module) -> set[str]:
    """Names listed in a module-level ``__all__`` literal (treated as public API)."""
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            names.update(elt.value for elt in node.value.elts if isinstance(elt, ast.Constant))
    return names


def _top_level_functions(tree: ast.Module) -> list[str]:
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("__")
    ]


def _count_refs(name: str, texts: list[str]) -> int:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    return sum(len(pattern.findall(text)) for text in texts)


def main() -> int:
    product_files = _py_files(PRODUCT_ROOT)
    product_texts = {p: p.read_text(encoding="utf-8", errors="ignore") for p in product_files}
    extra_product_texts = [
        p.read_text(encoding="utf-8", errors="ignore")
        for root in PRODUCT_REFERENCE_ROOTS
        if root != PRODUCT_ROOT
        for p in _py_files(root)
    ] + [
        (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        for name in ("pyproject.toml",)
        if (ROOT / name).is_file()
    ]
    test_texts = [
        p.read_text(encoding="utf-8", errors="ignore")
        for root in TEST_REFERENCE_ROOTS
        for p in _py_files(root)
    ]

    test_only: list[dict[str, object]] = []
    unreferenced: list[dict[str, object]] = []
    scanned = 0
    for path, text in product_texts.items():
        rel = path.relative_to(ROOT).as_posix()
        if path.name in {"__init__.py", "__main__.py"}:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        public = _module_all_names(tree)
        module_text = text
        for name in _top_level_functions(tree):
            scanned += 1
            if name in public:
                continue
            # Reference in the defining module, excluding the `def name` line itself.
            own = _count_refs(
                name,
                [
                    "\n".join(
                        ln
                        for ln in module_text.splitlines()
                        if not re.match(rf"\s*(async\s+)?def\s+{re.escape(name)}\b", ln)
                    )
                ],
            )
            other_product = _count_refs(
                name,
                [t for p, t in product_texts.items() if p != path] + extra_product_texts,
            )
            product_refs = own + other_product
            if product_refs > 0:
                continue
            test_refs = _count_refs(name, test_texts)
            entry = {"path": rel, "symbol": name, "testReferences": test_refs}
            if test_refs > 0:
                test_only.append(entry)
            else:
                unreferenced.append(entry)

    test_only.sort(key=lambda e: (e["path"], e["symbol"]))
    unreferenced.sort(key=lambda e: (e["path"], e["symbol"]))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 2,
        "scannedFunctionCount": scanned,
        "fullyUnreferencedCount": len(unreferenced),
        "testOnlyAdvisoryCount": len(test_only),
        "fullyUnreferenced": unreferenced[:100],
        "testOnlyAdvisory": test_only[:100],
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = "success" if not unreferenced else "review-required"
    print(f"DEAD_CODE_AUDIT_RESULT={result}")
    print(f"DEAD_CODE_REPORT={REPORT}")
    print(f"DEAD_CODE_SCANNED_FUNCTIONS={scanned}")
    print(f"DEAD_CODE_TEST_ONLY_ADVISORY={len(test_only)}")
    print(f"DEAD_CODE_FULLY_UNREFERENCED={len(unreferenced)}")
    return 0 if result == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
