#!/usr/bin/env python3
"""Validate and generate target capability documentation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_FILE = ROOT / "docs" / "target-validation.json"
BUNDLED_VALIDATION_FILE = ROOT / "spell_sync" / "bundled" / "target-validation.json"
SUPPORTED_DOC = ROOT / "docs" / "SUPPORTED_TARGETS.md"
START_MARKER = "[target-capabilities:start]"
END_MARKER = "[target-capabilities:end]"
LEGACY_MARKER = "```text target-capabilities-matrix"
LEGACY_HTML_START = "<!-- target-capabilities:start -->"
LEGACY_HTML_END = "<!-- target-capabilities:end -->"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.validate_target_validation_schema import (  # noqa: E402
    validate_target_validation_payload,
)

PRIVATE_PATH = re.compile(r"(~/|/Users/|/home/[^/\s]+/|C:\\Users\\)")


def _canonical_json(data: dict[str, object]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load_validation() -> dict[str, object]:
    return json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))


def _import_registry():
    sys.path.insert(0, str(ROOT))
    from spell_sync.target_capabilities import (  # noqa: WPS433
        TARGET_CAPABILITIES,
        capability_by_id,
        registry_target_platform_pairs,
    )

    return TARGET_CAPABILITIES, capability_by_id, registry_target_platform_pairs


def _validate(data: dict[str, object]) -> list[str]:
    errors = list(validate_target_validation_payload(data))
    if any(err.startswith(("targets:list", "missing:targets")) for err in errors):
        return errors

    entries = data.get("targets")
    if not isinstance(entries, list):
        return errors

    _, capability_by_id_fn, registry_pairs_fn = _import_registry()
    expected_pairs = set(registry_pairs_fn())
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        target_id = item.get("target_id")
        platform = item.get("platform")
        if not isinstance(target_id, str) or not isinstance(platform, str):
            continue
        key = (target_id, platform)
        if key in seen:
            errors.append(f"duplicate validation entry: {target_id}/{platform}")
        seen.add(key)
        capability = capability_by_id_fn(target_id)
        if capability is None:
            errors.append(f"unknown validation target_id: {target_id}")
            continue
        if platform not in capability.platforms:
            errors.append(f"platform {platform} not supported for target {target_id}")
        # Enum / date / manual-pass field rules are enforced by the schema shape validator.
        notes = item.get("notes")
        evidence = item.get("evidence")
        for field_name, value in (("notes", notes), ("evidence", evidence)):
            if isinstance(value, str) and PRIVATE_PATH.search(value):
                errors.append(f"{target_id}/{platform}: private path in {field_name}")

    missing = expected_pairs - seen
    for target_id, platform in sorted(missing):
        errors.append(f"missing validation entry: {target_id}/{platform}")
    extra = seen - expected_pairs
    for target_id, platform in sorted(extra):
        errors.append(f"unexpected validation entry: {target_id}/{platform}")
    return errors


def _render_matrix(data: dict[str, object]) -> str:
    _, capability_by_id_fn, _ = _import_registry()
    entries = data["targets"]
    assert isinstance(entries, list)
    header = (
        "Target | OS | Pull | Push | Filtering | Profiles | Close policy | "
        "Automated | Manual | Last real-app test"
    )
    separator = (
        "------ | -- | ---- | ---- | --------- | -------- | ------------ | "
        "--------- | ------ | ------------------"
    )
    lines = [header, separator]
    for item in sorted(entries, key=lambda row: (row["target_id"], row["platform"])):
        assert isinstance(item, dict)
        capability = capability_by_id_fn(str(item["target_id"]))
        assert capability is not None
        pull = "Yes" if capability.pull_supported else "No"
        push = "Yes" if capability.push_supported else "No"
        filtering = capability.filter_kind.value
        profiles = capability.profile_model.value
        close = capability.close_policy.value
        auto = item.get("automated_validation", "not-run")
        manual = item.get("manual_validation", "not-run")
        tested_on = item.get("tested_on") or "—"
        lines.append(
            f"{capability.display_name} | {item['platform']} | {pull} | {push} | "
            f"{filtering} | {profiles} | {close} | {auto} | {manual} | {tested_on}"
        )
    return "\n".join(lines)


def marker_structure_errors(text: str) -> list[str]:
    errors: list[str] = []
    if LEGACY_MARKER in text:
        errors.append("SUPPORTED_TARGETS.md: obsolete target-capabilities-matrix marker present")
    if LEGACY_HTML_START in text or LEGACY_HTML_END in text:
        errors.append("SUPPORTED_TARGETS.md: obsolete HTML target-capabilities markers present")
    start_count = text.count(START_MARKER)
    end_count = text.count(END_MARKER)
    if start_count != 1:
        errors.append(
            f"SUPPORTED_TARGETS.md: start marker must appear exactly once (found {start_count})"
        )
    if end_count != 1:
        errors.append(
            f"SUPPORTED_TARGETS.md: end marker must appear exactly once (found {end_count})"
        )
    if start_count != 1 or end_count != 1:
        return errors
    start = text.index(START_MARKER)
    end = text.index(END_MARKER)
    if end <= start:
        errors.append("SUPPORTED_TARGETS.md: end marker must appear after start marker")
    return errors


def extract_generated_content(text: str) -> str:
    start = text.index(START_MARKER) + len(START_MARKER)
    end = text.index(END_MARKER)
    return text[start:end].strip("\n")


def replace_generated_block(text: str, matrix: str) -> str:
    errors = marker_structure_errors(text)
    if errors:
        raise ValueError("; ".join(errors))
    start = text.index(START_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    block = f"{START_MARKER}\n{matrix}\n{END_MARKER}"
    return text[:start] + block + text[end:]


def _write_supported_doc(matrix: str) -> None:
    template = SUPPORTED_DOC.read_text(encoding="utf-8") if SUPPORTED_DOC.is_file() else ""
    try:
        updated = replace_generated_block(template, matrix)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    SUPPORTED_DOC.write_text(updated, encoding="utf-8")


def _write_bundled_validation(data: dict[str, object]) -> None:
    BUNDLED_VALIDATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUNDLED_VALIDATION_FILE.write_text(_canonical_json(data), encoding="utf-8")


def _check_supported_doc(data: dict[str, object]) -> list[str]:
    if not SUPPORTED_DOC.is_file():
        return ["missing docs/SUPPORTED_TARGETS.md"]
    text = SUPPORTED_DOC.read_text(encoding="utf-8")
    errors = marker_structure_errors(text)
    if errors:
        return errors
    expected = _render_matrix(data)
    actual = extract_generated_content(text)
    if actual != expected:
        return ["SUPPORTED_TARGETS.md generated matrix is stale — run --write"]
    return []


def _check_bundled_validation(data: dict[str, object]) -> list[str]:
    if not BUNDLED_VALIDATION_FILE.is_file():
        return ["missing spell_sync/bundled/target-validation.json"]
    expected = _canonical_json(data)
    actual = BUNDLED_VALIDATION_FILE.read_text(encoding="utf-8")
    if actual != expected:
        return ["bundled target-validation.json is stale — run --write"]
    if PRIVATE_PATH.search(actual):
        return ["bundled target-validation.json contains private path patterns"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate data and generated docs")
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate SUPPORTED_TARGETS.md matrix and bundled validation JSON",
    )
    args = parser.parse_args()
    if not args.check and not args.write:
        parser.error("specify --check and/or --write")

    data = _load_validation()
    errors = _validate(data)
    if args.write:
        if errors:
            print("Target capability write FAILED:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        _write_supported_doc(_render_matrix(data))
        _write_bundled_validation(data)
    if args.check:
        errors.extend(_check_supported_doc(data))
        errors.extend(_check_bundled_validation(data))
    if errors:
        print("Target capability check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Target capability check OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
