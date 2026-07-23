#!/usr/bin/env python3
"""Validate dependency group SSOT and contributor surface."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = pyproject.get("dependency-groups", {})
    project = pyproject.get("project", {})
    runtime = project.get("dependencies", [])
    optional = project.get("optional-dependencies", {}).get("dev", [])

    if "textual" not in " ".join(runtime):
        print("DEPENDENCY_GROUP_VALIDATION=failed")
        print("DEPENDENCY_GROUP_FAILED_ID=runtime-textual-missing")
        return 1
    for required in ("test-core", "coverage", "quality", "dev"):
        if required not in groups:
            print("DEPENDENCY_GROUP_VALIDATION=failed")
            print(f"DEPENDENCY_GROUP_FAILED_ID=missing-group:{required}")
            return 1
    dev_body = groups["dev"]
    if not any(
        isinstance(item, dict) and item.get("include-group") == "test-core" for item in dev_body
    ):
        print("DEPENDENCY_GROUP_VALIDATION=failed")
        print("DEPENDENCY_GROUP_FAILED_ID=dev-excludes-test-core")
        return 1
    if "twine" in str(groups.get("dev", "")):
        print("DEPENDENCY_GROUP_VALIDATION=failed")
        print("DEPENDENCY_GROUP_FAILED_ID=twine-in-default-dev")
        return 1
    if "packaging" not in groups or "release-check" not in groups:
        print("DEPENDENCY_GROUP_VALIDATION=failed")
        print("DEPENDENCY_GROUP_FAILED_ID=release-groups-missing")
        return 1
    if optional and "Deprecated" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        print("DEPENDENCY_GROUP_VALIDATION=failed")
        print("DEPENDENCY_GROUP_FAILED_ID=optional-dev-not-deprecated")
        return 1
    print("DEPENDENCY_GROUP_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
