"""Compute CI-relevant input identity for evidence reuse."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.ci_impact.constants import NON_CI_CHANGE_CLASSES, ChangeClass
from scripts.ci_impact.registry import (
    REGISTRY_REL_PATH,
    CiImpactRegistry,
    classify_path,
    is_excluded_path,
    load_registry,
    registry_digest,
)
from scripts.test_selection.tree_state import (
    GIT_SUBPROCESS_TIMEOUT_SECONDS,
    changed_source_paths,
    is_digest_excluded,
    normalize_rel,
)

CI_INPUT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CiInputState:
    digest: str
    files: tuple[str, ...]
    schema_version: int


def _run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return b""
    return result.stdout


def _is_ci_input_path(path: str, registry: CiImpactRegistry) -> bool:
    change_class = classify_path(path, registry)
    return change_class not in NON_CI_CHANGE_CLASSES and change_class != ChangeClass.UNKNOWN


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
    elif path.is_dir():
        hasher.update(b"dir:")
    else:
        hasher.update(b"missing:")
    hasher.update(b"\n")


def _tracked_ci_input_paths(root: Path, registry: CiImpactRegistry) -> tuple[str, ...]:
    raw = _run_git(root, "ls-files", "-z")
    paths: list[str] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        rel = normalize_rel(entry.decode("utf-8", errors="surrogateescape"))
        if _is_ci_input_path(rel, registry):
            paths.append(rel)
    if normalize_rel(REGISTRY_REL_PATH) not in paths and (root / REGISTRY_REL_PATH).is_file():
        paths.append(normalize_rel(REGISTRY_REL_PATH))
    return tuple(sorted(set(paths)))


def _deleted_ci_input_paths(root: Path, registry: CiImpactRegistry) -> tuple[str, ...]:
    raw = _run_git(root, "diff", "--name-only", "-z", "--diff-filter=D")
    deleted: list[str] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        rel = normalize_rel(entry.decode("utf-8", errors="surrogateescape"))
        if _is_ci_input_path(rel, registry):
            deleted.append(rel)
    return tuple(sorted(deleted))


def _ci_input_overlay_paths(root: Path, registry: CiImpactRegistry) -> tuple[str, ...]:
    overlay: set[str] = set()
    for rel in changed_source_paths(root):
        if is_digest_excluded(rel) or is_excluded_path(rel, registry):
            continue
        if _is_ci_input_path(rel, registry):
            overlay.add(rel)
    return tuple(sorted(overlay))


def compute_ci_input_state(root: Path, registry: CiImpactRegistry | None = None) -> CiInputState:
    registry = registry or load_registry(root / REGISTRY_REL_PATH)
    tracked = _tracked_ci_input_paths(root, registry)
    deleted = _deleted_ci_input_paths(root, registry)
    overlay = _ci_input_overlay_paths(root, registry)
    effective = sorted(set(tracked) | set(overlay))

    hasher = hashlib.sha256()
    hasher.update(b"schema:")
    hasher.update(str(CI_INPUT_SCHEMA_VERSION).encode("utf-8"))
    hasher.update(b"\nregistry:")
    hasher.update(registry_digest(registry).encode("utf-8"))
    hasher.update(b"\nimpact-schema:")
    hasher.update(str(registry.schema_version).encode("utf-8"))
    hasher.update(b"\ndeleted:\n")
    for rel in deleted:
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\n")
    hasher.update(b"\nfiles:\n")
    for rel in effective:
        _hash_path_entry(hasher, rel, root / rel)
    return CiInputState(
        digest=hasher.hexdigest(),
        files=tuple(effective),
        schema_version=CI_INPUT_SCHEMA_VERSION,
    )


def changed_ci_input_paths(root: Path, registry: CiImpactRegistry | None = None) -> tuple[str, ...]:
    registry = registry or load_registry(root / REGISTRY_REL_PATH)
    return tuple(
        sorted(
            rel
            for rel in changed_source_paths(root)
            if not is_digest_excluded(rel)
            and not is_excluded_path(rel, registry)
            and (
                _is_ci_input_path(rel, registry)
                or classify_path(rel, registry) == ChangeClass.UNKNOWN
            )
        )
    )
