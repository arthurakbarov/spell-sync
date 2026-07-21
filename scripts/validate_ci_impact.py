#!/usr/bin/env python3
"""Validate ci/ci-impact.toml registry integrity."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_impact.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    load_registry,
    validate_registry,
)


def main(argv: list[str] | None = None) -> int:
    del argv
    registry_path = ROOT / REGISTRY_REL_PATH
    if not registry_path.is_file():
        sys.stderr.write("[CI-IMPACT-SCHEMA-001] missing ci/ci-impact.toml\n")
        return 1
    try:
        registry = load_registry(registry_path)
    except ValueError as exc:
        sys.stderr.write(f"[CI-IMPACT-SCHEMA-001] {exc}\n")
        return 1
    errors = validate_registry(ROOT, registry)
    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    print("CI_IMPACT_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
