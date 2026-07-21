"""Documentation and agent-workflow identity for lightweight validation receipts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from scripts.ci_impact.constants import NON_CI_CHANGE_CLASSES, ChangeClass
from scripts.ci_impact.registry import (
    REGISTRY_REL_PATH,
    CiImpactRegistry,
    classify_path,
    load_registry,
)
from scripts.test_selection.tree_state import changed_source_paths, normalize_rel

DOCUMENTATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class DocumentationState:
    digest: str
    files: tuple[str, ...]
    change_classes: tuple[ChangeClass, ...]
    schema_version: int


def _is_documentation_path(path: str, registry: CiImpactRegistry) -> bool:
    return classify_path(path, registry) in NON_CI_CHANGE_CLASSES


def _hash_path_entry(hasher: hashlib._Hash, rel: str, path: Path) -> None:
    hasher.update(rel.encode("utf-8"))
    hasher.update(b"\0")
    if path.is_symlink():
        hasher.update(b"symlink:")
        hasher.update(os.readlink(path).encode("utf-8", errors="replace"))
    elif path.is_file():
        mode = path.stat().st_mode & 0o777
        hasher.update(f"file:{mode:o}:".encode("utf-8"))
        hasher.update(path.read_bytes())
    else:
        hasher.update(b"missing:")
    hasher.update(b"\n")


def _documentation_paths(root: Path, registry: CiImpactRegistry) -> tuple[str, ...]:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    paths: set[str] = set()
    if result.returncode == 0:
        for entry in result.stdout.split(b"\0"):
            if not entry:
                continue
            rel = normalize_rel(entry.decode("utf-8", errors="surrogateescape"))
            if _is_documentation_path(rel, registry):
                paths.add(rel)
    for rel in changed_source_paths(root):
        if _is_documentation_path(rel, registry):
            paths.add(rel)
    return tuple(sorted(paths))


def compute_documentation_state(
    root: Path,
    registry: CiImpactRegistry | None = None,
) -> DocumentationState:
    registry = registry or load_registry(root / REGISTRY_REL_PATH)
    files = _documentation_paths(root, registry)
    classes = sorted({classify_path(path, registry) for path in files}, key=lambda item: item.value)
    hasher = hashlib.sha256()
    hasher.update(b"schema:")
    hasher.update(str(DOCUMENTATION_SCHEMA_VERSION).encode("utf-8"))
    hasher.update(b"\nfiles:\n")
    for rel in files:
        _hash_path_entry(hasher, rel, root / rel)
    return DocumentationState(
        digest=hasher.hexdigest(),
        files=files,
        change_classes=tuple(classes),
        schema_version=DOCUMENTATION_SCHEMA_VERSION,
    )
