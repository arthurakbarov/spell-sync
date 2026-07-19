#!/usr/bin/env python3
"""Validate and generate target capability documentation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_FILE = ROOT / "docs" / "target-validation.json"
SUPPORTED_DOC = ROOT / "docs" / "SUPPORTED_TARGETS.md"
MATRIX_START = "```text target-capabilities-matrix"
MATRIX_END = "```"

IMPLEMENTATION_STATUSES = {"implemented", "experimental", "not-implemented"}
AUTOMATED_STATUSES = {"pass", "fail", "partial", "not-run"}
MANUAL_STATUSES = {"pass", "fail", "not-run", "experimental"}
PRIVATE_PATH = re.compile(r"(~/|/Users/|/home/[^/\s]+/|C:\\Users\\)")


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
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("target-validation.json: schema_version must be 1")
    entries = data.get("targets")
    if not isinstance(entries, list):
        errors.append("target-validation.json: targets must be a list")
        return errors

    _, capability_by_id_fn, registry_pairs_fn = _import_registry()
    expected_pairs = set(registry_pairs_fn())
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            errors.append(f"targets[{index}] must be an object")
            continue
        target_id = item.get("target_id")
        platform = item.get("platform")
        if not isinstance(target_id, str) or not isinstance(platform, str):
            errors.append(f"targets[{index}] requires target_id and platform strings")
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
        impl = item.get("implementation")
        auto = item.get("automated_validation")
        manual = item.get("manual_validation")
        if impl not in IMPLEMENTATION_STATUSES:
            errors.append(f"{target_id}/{platform}: invalid implementation status")
        if auto not in AUTOMATED_STATUSES:
            errors.append(f"{target_id}/{platform}: invalid automated_validation status")
        if manual not in MANUAL_STATUSES:
            errors.append(f"{target_id}/{platform}: invalid manual_validation status")
        tested_on = item.get("tested_on")
        if tested_on is not None:
            try:
                date.fromisoformat(str(tested_on))
            except ValueError:
                errors.append(f"{target_id}/{platform}: invalid tested_on date")
        if manual == "pass":
            if not item.get("application_version"):
                errors.append(f"{target_id}/{platform}: manual pass requires application_version")
            if not tested_on:
                errors.append(f"{target_id}/{platform}: manual pass requires tested_on")
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


def _write_supported_doc(matrix: str) -> None:
    template = SUPPORTED_DOC.read_text(encoding="utf-8") if SUPPORTED_DOC.is_file() else ""
    block = f"{MATRIX_START}\n{matrix}\n{MATRIX_END}"
    marker = MATRIX_START
    if marker in template:
        start = template.index(marker)
        end = template.index(MATRIX_END, start) + len(MATRIX_END)
        updated = template[:start] + block + template[end:]
    else:
        updated = template.rstrip() + "\n\n" + block + "\n"
    SUPPORTED_DOC.write_text(updated, encoding="utf-8")


def _check_supported_doc(data: dict[str, object]) -> list[str]:
    if not SUPPORTED_DOC.is_file():
        return ["missing docs/SUPPORTED_TARGETS.md"]
    expected = _render_matrix(data)
    text = SUPPORTED_DOC.read_text(encoding="utf-8")
    if MATRIX_START not in text:
        return ["SUPPORTED_TARGETS.md: missing generated matrix block"]
    start = text.index(MATRIX_START) + len(MATRIX_START) + 1
    end = text.index(MATRIX_END, start)
    actual = text[start:end].strip()
    if actual != expected.strip():
        return ["SUPPORTED_TARGETS.md generated matrix is stale — run --write"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate data and generated docs")
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate SUPPORTED_TARGETS.md matrix",
    )
    args = parser.parse_args()
    if not args.check and not args.write:
        parser.error("specify --check and/or --write")

    data = _load_validation()
    errors = _validate(data)
    if args.write:
        _write_supported_doc(_render_matrix(data))
    if args.check:
        errors.extend(_check_supported_doc(data))
    if errors:
        print("Target capability check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Target capability check OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
