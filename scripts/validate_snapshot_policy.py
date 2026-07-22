#!/usr/bin/env python3
"""Validate snapshot policy, exclusions, atomic output, and documentation boundaries."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_POLICY = Path("/Users/arthurakbarov/code/spell-sync-dev/snapshot-policy.toml")
DEFAULT_SNAPSHOT_SCRIPT = Path(
    "/Users/arthurakbarov/code/spell-sync-dev/scripts/create-code-snapshot.py"
)

DOC_PATHS = (
    ROOT / "docs" / "AGENT_DEVELOPMENT.md",
    ROOT / "docs" / "DEVELOPMENT.md",
    ROOT / "docs" / "SUPPORTED_ENVIRONMENTS.md",
)

TMP_CP_WORKAROUND = re.compile(
    r"/tmp.*\bcp\b.*code\.zip|create.*in\s+/tmp.*code\.zip|code\.zip.*\bcp\b.*/tmp",
    re.IGNORECASE | re.DOTALL,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _resolve_snapshot_dev_paths() -> tuple[Path, Path]:
    env_root = os.environ.get("SPELL_SYNC_DEV_ROOT", "").strip()
    if env_root:
        dev_root = Path(env_root).expanduser().resolve()
        return (
            dev_root / "snapshot-policy.toml",
            dev_root / "scripts" / "create-code-snapshot.py",
        )
    if DEFAULT_SNAPSHOT_POLICY.is_file() and DEFAULT_SNAPSHOT_SCRIPT.is_file():
        return DEFAULT_SNAPSHOT_POLICY, DEFAULT_SNAPSHOT_SCRIPT
    candidates = (
        ROOT.parent.parent / "spell-sync-dev",
        ROOT.parent / "spell-sync-dev",
    )
    for candidate in candidates:
        policy = candidate / "snapshot-policy.toml"
        script = candidate / "scripts" / "create-code-snapshot.py"
        if policy.is_file() and script.is_file():
            return policy.resolve(), script.resolve()
    return DEFAULT_SNAPSHOT_POLICY, DEFAULT_SNAPSHOT_SCRIPT


def _check_snapshot_policy(policy_path: Path) -> list[str]:
    errors: list[str] = []
    if not policy_path.is_file():
        errors.append(
            f"[SNAPSHOT-POLICY-008] missing snapshot policy at {policy_path}; "
            "remediation: add spell-sync-dev/snapshot-policy.toml"
        )
        return errors
    try:
        data = tomllib.loads(_read(policy_path))
    except tomllib.TOMLDecodeError as exc:
        errors.append(
            f"[SNAPSHOT-POLICY-008] invalid snapshot-policy.toml: {exc}; "
            "remediation: fix TOML syntax"
        )
        return errors
    exclusions = data.get("exclusions", {})
    patterns: list[str] = []
    if isinstance(exclusions, dict):
        raw_patterns = exclusions.get("patterns")
        if isinstance(raw_patterns, list):
            patterns = [str(item) for item in raw_patterns]
    if not any(".venv" in pattern for pattern in patterns):
        errors.append(
            "[SNAPSHOT-POLICY-008] snapshot-policy.toml must exclude .venv paths; "
            "remediation: add .venv/ and **/.venv/ to [exclusions].patterns"
        )
    required_inputs = data.get("requiredEnvironmentInputs", {})
    required_patterns: list[str] = []
    if isinstance(required_inputs, dict):
        raw_required = required_inputs.get("patterns")
        if isinstance(raw_required, list):
            required_patterns = [str(item) for item in raw_required]
    for required in (
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "config/environment-contract.toml",
    ):
        if required not in required_patterns:
            errors.append(
                f"[SNAPSHOT-POLICY-008] snapshot-policy.toml must retain {required}; "
                "remediation: add to [requiredEnvironmentInputs].patterns"
            )
    retained = data.get("retainedArtifacts", {})
    retained_patterns: list[str] = []
    if isinstance(retained, dict):
        raw_retained = retained.get("patterns")
        if isinstance(raw_retained, list):
            retained_patterns = [str(item) for item in raw_retained]
    if ".artifacts/environment/environment.json" not in retained_patterns:
        errors.append(
            "[SNAPSHOT-POLICY-008] snapshot-policy.toml must retain environment evidence; "
            "remediation: add .artifacts/environment/environment.json to retainedArtifacts"
        )
    return errors


def _check_snapshot_script(script_path: Path) -> list[str]:
    errors: list[str] = []
    if not script_path.is_file():
        errors.append(
            f"[SNAPSHOT-POLICY-008] missing create-code-snapshot.py at {script_path}; "
            "remediation: restore maintainer snapshot script"
        )
        return errors
    text = _read(script_path)
    if "snapshot_policy" not in text and "_load_policy" not in text:
        errors.append(
            "[SNAPSHOT-POLICY-012] create-code-snapshot.py must load shared snapshot_policy parser"
        )
    if "should_skip_workspace_path" not in text:
        errors.append(
            "[SNAPSHOT-POLICY-012] create-code-snapshot.py must apply policy matcher "
            "during archive creation"
        )
    if "snapshotPolicySha256" not in text:
        errors.append(
            "[SNAPSHOT-POLICY-012] snapshot manifest must include snapshotPolicySha256 digest"
        )
    if "_require_environment_evidence" not in text:
        errors.append(
            "[SNAPSHOT-ENVIRONMENT-010] create-code-snapshot.py must require environment evidence"
        )
    policy_file = script_path.parent.parent / "snapshot-policy.toml"
    if policy_file.is_file() and ".spell-sync.lock" not in _read(policy_file):
        errors.append("[SNAPSHOT-POLICY-012] snapshot-policy.toml must exclude .spell-sync.lock")
    if ".venv" not in text:
        errors.append(
            "[SNAPSHOT-POLICY-008] create-code-snapshot.py must exclude .venv entries; "
            "remediation: load snapshot-policy exclusions or skip .venv paths"
        )
    fsync_markers = ("_fsync_path", "os.fsync", "fcntl.fsync")
    if not any(marker in text for marker in fsync_markers):
        errors.append(
            "[SNAPSHOT-ATOMIC-009] create-code-snapshot.py must fsync candidate and parent "
            "directory; remediation: add _fsync_path helper and call it before os.replace"
        )
    if "os.replace(" not in text:
        errors.append(
            "[SNAPSHOT-ATOMIC-009] create-code-snapshot.py must atomically replace final output; "
            "remediation: write candidate beside output and os.replace into place"
        )
    if ".code.zip.tmp-" not in text:
        errors.append(
            "[SNAPSHOT-ATOMIC-009] create-code-snapshot.py must use beside-output candidate names; "
            "remediation: create .code.zip.tmp-<token> next to final output"
        )
    if '"environment"' not in text or "environmentEvidenceSha256" not in text:
        errors.append(
            "[SNAPSHOT-ENVIRONMENT-010] create-code-snapshot.py manifest must bind "
            "environment digests"
        )
    if "SCHEMA_VERSION = 2" not in text and 'schemaVersion": 2' not in text:
        errors.append(
            "[SNAPSHOT-ENVIRONMENT-010] snapshot manifest schema must be version 2 "
            "with environment block"
        )
    return errors


def _check_docs_home_snapshot_path() -> list[str]:
    errors: list[str] = []
    agent_dev = ROOT / "docs" / "AGENT_DEVELOPMENT.md"
    if not agent_dev.is_file():
        return errors
    text = _read(agent_dev)
    if "$HOME/code.zip" not in text:
        errors.append(
            "[SNAPSHOT-PATH-011] AGENT_DEVELOPMENT.md must require canonical "
            "$HOME/code.zip output; remediation: document home-directory snapshot path "
            "in § Workspace snapshot"
        )
    forbidden_markers = (
        "$SPELL_SYNC_WORKSPACE/code.zip",
        "~/code/code.zip",
        "workspace tree",
    )
    if not any(marker in text for marker in forbidden_markers):
        errors.append(
            "[SNAPSHOT-PATH-011] AGENT_DEVELOPMENT.md must forbid workspace-tree code.zip paths; "
            "remediation: state archive must not live under workspace directories"
        )
    return errors


def _check_docs_no_tmp_workaround() -> list[str]:
    errors: list[str] = []
    for path in DOC_PATHS:
        if not path.is_file():
            continue
        text = _read(path)
        if TMP_CP_WORKAROUND.search(text):
            errors.append(
                f"[SNAPSHOT-ATOMIC-009] {path.relative_to(ROOT)} documents /tmp+cp snapshot "
                "workaround; remediation: document direct atomic --output only"
            )
    return errors


def main() -> int:
    policy_path, script_path = _resolve_snapshot_dev_paths()
    errors: list[str] = []
    errors.extend(_check_snapshot_policy(policy_path))
    errors.extend(_check_snapshot_script(script_path))
    errors.extend(_check_docs_home_snapshot_path())
    errors.extend(_check_docs_no_tmp_workaround())

    if errors:
        for item in errors:
            print(item)
        print(f"SNAPSHOT_POLICY_VALIDATION=failed checks={len(errors)}")
        return 1
    print("SNAPSHOT_POLICY_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
