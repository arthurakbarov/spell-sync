"""Load and validate the CI impact registry."""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    CLASS_SECTION_KEYS,
    FULL_CI_CHANGE_CLASSES,
    ChangeClass,
)

REGISTRY_REL_PATH = "ci/ci-impact.toml"
SCHEMA_VERSION_KEY = "schemaVersion"
ALLOWED_TOP_KEYS = frozenset(
    {"schemaVersion", "meta", "excluded", "allowedUnclassified", "classes"}
)
ALLOWED_META_KEYS = frozenset({"registryPath", "impactModule"})
ALLOWED_CLASS_SECTION_KEYS = frozenset(CLASS_SECTION_KEYS.values())


@dataclass(frozen=True, slots=True)
class CiImpactRegistry:
    schema_version: int
    path: Path
    excluded_patterns: tuple[str, ...]
    allowed_unclassified_patterns: tuple[str, ...]
    class_patterns: dict[ChangeClass, tuple[str, ...]]


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _glob_to_regex(pattern: str) -> str:
    import re

    pieces = ["^"]
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            pieces.append(".*")
            index += 2
            continue
        char = pattern[index]
        if char == "*":
            pieces.append("[^/]*")
            index += 1
            continue
        if char == "?":
            pieces.append("[^/]")
            index += 1
            continue
        end = index
        while end < len(pattern) and pattern[end] not in "*?":
            end += 1
        pieces.append(re.escape(pattern[index:end]))
        index = end
    pieces.append("$")
    return "".join(pieces)


def _path_matches(path: str, pattern: str) -> bool:
    import fnmatch
    import re

    normalized = _normalize(path)
    if normalized == pattern.rstrip("/"):
        return True
    if pattern.endswith("/") and normalized.startswith(pattern):
        return True
    if "**" in pattern or "?" in pattern:
        return re.fullmatch(_glob_to_regex(pattern), normalized) is not None
    return fnmatch.fnmatch(normalized, pattern)


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(_path_matches(path, pattern) for pattern in patterns)


def _is_excluded(path: str, registry: CiImpactRegistry) -> bool:
    return _matches_any(path, registry.excluded_patterns)


def is_excluded_path(path: str, registry: CiImpactRegistry) -> bool:
    return _is_excluded(_normalize(path), registry)


def _is_allowed_unclassified(path: str, registry: CiImpactRegistry) -> bool:
    return _matches_any(path, registry.allowed_unclassified_patterns)


def _as_patterns(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def load_registry(path: Path) -> CiImpactRegistry:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("ci impact registry must be a TOML table")
    schema_version = data.get("schemaVersion")
    if schema_version != 1:
        raise ValueError(f"unsupported ci impact schemaVersion: {schema_version!r}")

    for key in data:
        if key not in ALLOWED_TOP_KEYS:
            raise ValueError(f"unknown top-level key: {key}")

    meta = data.get("meta", {})
    if meta and not isinstance(meta, dict):
        raise ValueError("meta must be a table")
    for key in meta:
        if key not in ALLOWED_META_KEYS:
            raise ValueError(f"unknown meta key: {key}")

    excluded = _as_patterns((data.get("excluded") or {}).get("patterns"))
    allowed = _as_patterns((data.get("allowedUnclassified") or {}).get("patterns"))

    classes_raw = data.get("classes", {})
    if not isinstance(classes_raw, dict):
        raise ValueError("classes must be a table")

    class_patterns: dict[ChangeClass, tuple[str, ...]] = {}
    for change_class, section_key in CLASS_SECTION_KEYS.items():
        section = classes_raw.get(section_key, {})
        if section is None:
            section = {}
        if not isinstance(section, dict):
            raise ValueError(f"classes.{section_key} must be a table")
        for key in section:
            if key != "patterns":
                raise ValueError(f"unknown classes.{section_key} key: {key}")
        class_patterns[change_class] = _as_patterns(section.get("patterns"))

    for section_key in classes_raw:
        if section_key not in ALLOWED_CLASS_SECTION_KEYS:
            raise ValueError(f"unknown classes section: {section_key}")

    return CiImpactRegistry(
        schema_version=int(schema_version),
        path=path,
        excluded_patterns=excluded,
        allowed_unclassified_patterns=allowed,
        class_patterns=class_patterns,
    )


def registry_digest(registry: CiImpactRegistry) -> str:
    return hashlib.sha256(registry.path.read_bytes()).hexdigest()


def matching_classes(path: str, registry: CiImpactRegistry) -> tuple[ChangeClass, ...]:
    normalized = _normalize(path)
    if _is_excluded(normalized, registry):
        return ()
    matched: list[ChangeClass] = []
    for change_class, patterns in registry.class_patterns.items():
        if _matches_any(normalized, patterns):
            matched.append(change_class)
    return tuple(matched)


def classify_path(path: str, registry: CiImpactRegistry) -> ChangeClass:
    normalized = _normalize(path)
    if _is_excluded(normalized, registry):
        return ChangeClass.UNKNOWN
    if _is_allowed_unclassified(normalized, registry):
        return ChangeClass.REPOSITORY_METADATA
    matched = matching_classes(normalized, registry)
    if not matched:
        return ChangeClass.UNKNOWN
    if len(matched) == 1:
        return matched[0]
    # Deterministic tie-break using CLASS_PRIORITY order.
    from .constants import CLASS_PRIORITY

    for change_class in CLASS_PRIORITY:
        if change_class in matched:
            return change_class
    return ChangeClass.UNKNOWN


def classify_paths(
    paths: list[str] | tuple[str, ...],
    registry: CiImpactRegistry,
) -> dict[str, ChangeClass]:
    return {path: classify_path(path, registry) for path in paths}


def requires_full_ci(change_class: ChangeClass) -> bool:
    return change_class in FULL_CI_CHANGE_CLASSES


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    paths: list[str] = []
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        paths.append(entry.decode("utf-8", errors="surrogateescape"))
    return sorted(paths)


def validate_registry(root: Path, registry: CiImpactRegistry) -> list[str]:
    errors: list[str] = []
    tracked = _tracked_paths(root)

    for change_class, patterns in registry.class_patterns.items():
        section = CLASS_SECTION_KEYS[change_class]
        for left_class, left_patterns in registry.class_patterns.items():
            if left_class.value >= change_class.value:
                continue
            left_section = CLASS_SECTION_KEYS[left_class]
            for left_pattern in left_patterns:
                for right_pattern in patterns:
                    if left_pattern == right_pattern:
                        errors.append(
                            f"[CI-IMPACT-OVERLAP-001] duplicate pattern {left_pattern!r} "
                            f"in classes.{left_section} and classes.{section}"
                        )

    for path in tracked:
        normalized = _normalize(path)
        if _is_excluded(normalized, registry):
            continue
        if _is_allowed_unclassified(normalized, registry):
            continue
        matched = matching_classes(normalized, registry)
        if not matched:
            errors.append(
                f"[CI-IMPACT-UNKNOWN-001] tracked path {normalized!r} is not classified "
                "remediation: add a matching pattern to ci/ci-impact.toml"
            )
            continue
        if len(matched) > 1:
            sections = ", ".join(CLASS_SECTION_KEYS[item] for item in matched)
            errors.append(
                f"[CI-IMPACT-OVERLAP-002] tracked path {normalized!r} matches multiple "
                f"classes: {sections}"
            )

    return errors
