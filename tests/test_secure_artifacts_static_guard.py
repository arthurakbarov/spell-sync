"""Static guard: forbidden patterns in security-sensitive modules."""

from __future__ import annotations

import ast
from pathlib import Path

SECURE_MODULE_PATHS = (
    Path("spell_sync/trusted_internal_fs.py"),
    Path("spell_sync/secure_artifacts.py"),
)

FORBIDDEN_PATH_ATTRS = frozenset({"read_text", "write_text", "unlink", "iterdir", "rmdir"})


class _SecureGuardVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []
        self._skip_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        is_win = node.name.startswith("_win_")
        if is_win:
            self._skip_depth += 1
        self.generic_visit(node)
        if is_win:
            self._skip_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if self._skip_depth:
            return
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "resolve" and isinstance(func.value, ast.Name) and func.value.id == "Path":
                self.violations.append(f"{self.path}:{node.lineno}: Path.resolve() forbidden")
            if func.attr == "rmtree" and isinstance(func.value, ast.Name) and func.value.id == "shutil":
                self.violations.append(f"{self.path}:{node.lineno}: shutil.rmtree() forbidden")
        if isinstance(func, ast.Name) and func.id == "chmod":
            self.violations.append(f"{self.path}:{node.lineno}: os.chmod() forbidden")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self._skip_depth:
            return
        if isinstance(node.value, ast.Name):
            if node.value.id == "Path" and node.attr in FORBIDDEN_PATH_ATTRS:
                self.violations.append(f"{self.path}:{node.lineno}: Path.{node.attr} forbidden")
        self.generic_visit(node)


def _find_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _SecureGuardVisitor(path)
    visitor.visit(tree)
    return visitor.violations


def test_secure_modules_forbidden_patterns() -> None:
    repo = Path(__file__).resolve().parents[1]
    all_violations: list[str] = []
    for rel in SECURE_MODULE_PATHS:
        all_violations.extend(_find_violations(repo / rel))
    assert not all_violations, "\n".join(all_violations)
