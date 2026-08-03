#!/usr/bin/env python3
"""Run lightweight validators for non-CI documentation and workflow changes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_impact.constants import NON_CI_CHANGE_CLASSES, ChangeClass  # noqa: E402
from scripts.ci_impact.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    classify_path,
    load_registry,
)
from scripts.documentation_state import (  # noqa: E402
    DOCUMENTATION_SCHEMA_VERSION,
    compute_documentation_state,
)
from scripts.environment_contract.paths import (  # noqa: E402
    EnvironmentPaths,
    production_environment_paths,
)
from scripts.test_selection.tree_state import changed_source_paths, git_head  # noqa: E402

RECEIPT_REL_PATH = Path(".artifacts") / "lightweight-validation" / "current.json"


def _run(command: list[str], *, cwd: Path = ROOT) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr:
        if output and not output.endswith("\n"):
            output += "\n"
        output += proc.stderr
    return proc.returncode, output.rstrip()


def _changed_classes(root: Path) -> set[ChangeClass]:
    registry = load_registry(root / REGISTRY_REL_PATH)
    classes = {classify_path(path, registry) for path in changed_source_paths(root)}
    return {
        item for item in classes if item in NON_CI_CHANGE_CLASSES or item == ChangeClass.VALIDATOR
    }


def _commands_for_classes(classes: set[ChangeClass]) -> list[list[str]]:
    py = sys.executable
    commands: list[list[str]] = []
    if ChangeClass.DOCUMENTATION in classes or ChangeClass.AGENT_WORKFLOW in classes:
        commands.extend(
            [
                ["bash", "scripts/check-docs-style.sh"],
                [py, "scripts/check_docs_contract.py"],
            ]
        )
    if ChangeClass.AGENT_WORKFLOW in classes:
        commands.append([py, "scripts/check_agent_config.py"])
    if ChangeClass.REPOSITORY_METADATA in classes:
        commands.append([py, "scripts/validate_ci_impact.py"])
    if ChangeClass.VALIDATOR in classes:
        commands.append([py, "scripts/validate_ci_impact.py"])
    # Architecture tracker / ADR consistency is covered by docs contract.
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            deduped.append(command)
    return deduped


def run_lightweight_validation(
    root: Path,
    *,
    paths: EnvironmentPaths | None = None,
) -> tuple[int, dict[str, object]]:
    env_paths = paths or production_environment_paths(root)
    registry = load_registry(root / REGISTRY_REL_PATH)
    doc_state = compute_documentation_state(root, registry)
    classes = set(doc_state.change_classes)
    classes.update(_changed_classes(root))
    classes = {item for item in classes if item != ChangeClass.UNKNOWN}
    if not classes:
        classes = {ChangeClass.DOCUMENTATION}

    commands = _commands_for_classes(classes)
    git_diff_check = subprocess.run(
        ["git", "-C", str(root), "diff", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    executed: list[dict[str, object]] = []
    if git_diff_check.returncode != 0:
        return 1, {
            "result": "failed",
            "failedId": "lightweight.git-diff-check",
            "detail": git_diff_check.stdout + git_diff_check.stderr,
        }

    for command in commands:
        rc, output = _run(command, cwd=root)
        executed.append({"argv": command, "exitCode": rc, "output": output[-4000:]})
        if rc != 0:
            return 1, {
                "result": "failed",
                "failedId": "lightweight.command-failed",
                "command": command,
                "executed": executed,
            }

    head = git_head(root)
    receipt = {
        "schemaVersion": DOCUMENTATION_SCHEMA_VERSION,
        "gitHead": head,
        "documentationDigest": doc_state.digest,
        "changeClasses": sorted(item.value for item in classes),
        "commands": executed,
        "result": "success",
        "completedAt": (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ),
    }
    receipt_path = env_paths.lightweight_receipt_root / "current.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight validation for non-CI changes.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    code, payload = run_lightweight_validation(ROOT)
    receipt_path = production_environment_paths(ROOT).lightweight_receipt_root / "current.json"
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"LIGHTWEIGHT_VALIDATION_RESULT={'success' if code == 0 else 'failed'}")
        if code == 0:
            print(f"LIGHTWEIGHT_RECEIPT={receipt_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
