#!/usr/bin/env python3
"""Verify CI summary evidence against repository and CI input identity."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_history import summarize_ci_history  # noqa: E402
from scripts.ci_impact.constants import (  # noqa: E402
    FULL_CI_CHANGE_CLASSES,
    ChangeClass,
)
from scripts.ci_impact.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    classify_path,
    is_excluded_path,
    load_registry,
)
from scripts.ci_input_state import changed_ci_input_paths, compute_ci_input_state  # noqa: E402
from scripts.documentation_state import compute_documentation_state  # noqa: E402
from scripts.environment_contract.evidence import (  # noqa: E402
    read_environment_evidence,
)
from scripts.environment_contract.fingerprint import (  # noqa: E402
    resolve_project_environment_fingerprint,
)
from scripts.environment_contract.paths import (  # noqa: E402
    EnvironmentPaths,
    production_environment_paths,
)
from scripts.test_selection.tree_state import (  # noqa: E402
    changed_source_paths,
    content_tree_digest,
    git_branch,
    git_detached,
    git_head,
    is_digest_excluded,
    is_working_tree_clean,
)

SUPPORTED_SCHEMAS = frozenset({3, 4, 5})


def _fail(
    failed_id: str,
    *,
    head: str = "",
    digest: str = "",
    run_id: str = "",
    match: str = "",
    run_head: str = "",
) -> int:
    print("CI_EVIDENCE_RESULT=failed")
    print(f"CI_EVIDENCE_FAILED_ID={failed_id}")
    if head:
        print(f"CI_EVIDENCE_HEAD={head}")
    if digest:
        print(f"CI_EVIDENCE_TREE_DIGEST={digest}")
    if run_id:
        print(f"CI_EVIDENCE_RUN_ID={run_id}")
    if match:
        print(f"CI_EVIDENCE_MATCH={match}")
    if run_head:
        print(f"CI_EVIDENCE_RUN_HEAD={run_head}")
    return 1


def _success(
    *,
    head: str,
    digest: str,
    run_id: str,
    match: str,
    run_head: str = "",
    ci_input_digest: str = "",
) -> int:
    print("CI_EVIDENCE_RESULT=success")
    print(f"CI_EVIDENCE_MATCH={match}")
    print(f"CI_EVIDENCE_HEAD={head}")
    if run_head and run_head != head:
        print(f"CI_EVIDENCE_CURRENT_HEAD={head}")
        print(f"CI_EVIDENCE_RUN_HEAD={run_head}")
    print(f"CI_EVIDENCE_TREE_DIGEST={digest}")
    if ci_input_digest:
        print(f"CI_EVIDENCE_CI_INPUT_DIGEST={ci_input_digest}")
    print(f"CI_EVIDENCE_RUN_ID={run_id}")
    return 0


def _failure_result(
    failed_id: str,
    *,
    head: str,
    digest: str,
    run_id: str = "",
    match: str = "",
) -> dict[str, object]:
    result: dict[str, object] = {
        "result": "failed",
        "failedId": failed_id,
        "gitHead": head,
        "treeDigest": digest,
    }
    if run_id:
        result["runId"] = run_id
    if match:
        result["match"] = match
    return result


def _reject(
    failed_id: str,
    *,
    head: str,
    digest: str,
    run_id: str = "",
    format_json: bool,
    match: str = "",
) -> tuple[int, dict[str, object]]:
    result = _failure_result(failed_id, head=head, digest=digest, run_id=run_id, match=match)
    if not format_json:
        _fail(failed_id, head=head, digest=digest, run_id=run_id, match=match)
    return 1, result


def _summary_run_head(payload: dict[str, object]) -> str:
    for key in ("gitHeadAtRun", "gitHead"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _committed_diff_paths(root: Path, base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "-z", f"{base}..{head}"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        return []
    return [
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in proc.stdout.split(b"\0")
        if item
    ]


def _uv_version() -> str:
    import re

    proc = subprocess.run(["uv", "--version"], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return ""
    match = re.search(r"uv\s+(\d+\.\d+\.\d+)", proc.stdout)
    return match.group(1) if match else ""


def _current_environment_fingerprint(root: Path) -> str:
    fingerprint = resolve_project_environment_fingerprint(root, uv_version=_uv_version())
    if fingerprint is None:
        return ""
    return fingerprint.signature()


def _validate_environment_identity(
    root: Path,
    payload: dict[str, object],
) -> str | None:
    summary_fp = payload.get("environmentFingerprint")
    if not isinstance(summary_fp, str) or not summary_fp:
        if payload.get("schemaVersion", 0) >= 5:
            return "ci-evidence.environment-mismatch"
        return None
    current_fp = _current_environment_fingerprint(root)
    if not current_fp or current_fp != summary_fp:
        return "ci-evidence.environment-mismatch"
    before_fp = payload.get("environmentFingerprintBefore")
    after_fp = payload.get("environmentFingerprintAfter")
    if isinstance(before_fp, str) and isinstance(after_fp, str) and before_fp != after_fp:
        return "ci-evidence.environment-mismatch"
    if payload.get("environmentStable") is False:
        return "ci-evidence.environment-mismatch"
    fingerprint = resolve_project_environment_fingerprint(root, uv_version=_uv_version())
    if fingerprint is None:
        return "ci-evidence.environment-mismatch"
    digest_checks = (
        ("environmentContractDigest", fingerprint.environment_contract_digest),
        ("pyprojectDigest", fingerprint.pyproject_digest),
        ("uvLockDigest", fingerprint.uv_lock_digest),
        ("installedEnvironmentDigest", fingerprint.installed_environment_digest),
        ("pythonVersion", fingerprint.python_version),
        ("pythonImplementation", fingerprint.python_implementation),
        ("pythonCacheTag", fingerprint.python_cache_tag),
        ("uvVersion", fingerprint.uv_version),
    )
    for key, expected in digest_checks:
        value = payload.get(key)
        if isinstance(value, str) and value and value != expected:
            return "ci-evidence.environment-mismatch"
    return None


def _validate_environment_evidence(
    root: Path,
    payload: dict[str, object],
    *,
    head: str,
    env_paths: EnvironmentPaths,
) -> str | None:
    evidence = read_environment_evidence(root, paths=env_paths)
    if evidence is None:
        return "ci-evidence.environment-mismatch"
    if evidence.schema_version < 1:
        return "ci-evidence.environment-mismatch"
    if evidence.environment_check_exit != 0 or evidence.lock_check_exit != 0:
        return "ci-evidence.environment-mismatch"
    if evidence.repository_head and evidence.repository_head != head:
        return "ci-evidence.environment-mismatch"
    fingerprint = resolve_project_environment_fingerprint(root, uv_version=_uv_version())
    if fingerprint is None:
        return "ci-evidence.environment-mismatch"
    if evidence.environment_fingerprint != fingerprint.signature():
        return "ci-evidence.environment-mismatch"
    summary_fp = payload.get("environmentFingerprint")
    if (
        isinstance(summary_fp, str)
        and summary_fp
        and summary_fp != evidence.environment_fingerprint
    ):
        return "ci-evidence.environment-mismatch"
    live_checks = {
        "environmentContractDigest": fingerprint.environment_contract_digest,
        "pyprojectDigest": fingerprint.pyproject_digest,
        "uvLockDigest": fingerprint.uv_lock_digest,
        "installedEnvironmentDigest": fingerprint.installed_environment_digest,
        "pythonVersion": fingerprint.python_version,
        "pythonImplementation": fingerprint.python_implementation,
        "pythonCacheTag": fingerprint.python_cache_tag,
        "uvVersion": fingerprint.uv_version,
    }
    evidence_checks = {
        "environmentContractDigest": evidence.environment_contract_digest,
        "pyprojectDigest": evidence.pyproject_digest,
        "uvLockDigest": evidence.uv_lock_digest,
        "installedEnvironmentDigest": evidence.installed_environment_digest,
        "pythonVersion": evidence.python_version,
        "pythonImplementation": evidence.python_implementation,
        "pythonCacheTag": evidence.python_cache_tag,
        "uvVersion": evidence.uv_version,
    }
    for key, live in live_checks.items():
        if evidence_checks[key] != live:
            return "ci-evidence.environment-mismatch"
        summary_value = payload.get(key)
        if isinstance(summary_value, str) and summary_value and summary_value != live:
            return "ci-evidence.environment-mismatch"
    return None


def _validate_lightweight_receipt(root: Path, head: str, *, paths: EnvironmentPaths) -> str | None:
    receipt_path = paths.lightweight_receipt_root / "current.json"
    if not receipt_path.is_file():
        return "ci-evidence.lightweight-evidence-missing"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return "ci-evidence.lightweight-evidence-stale"
    if not isinstance(receipt, dict):
        return "ci-evidence.lightweight-evidence-stale"
    if receipt.get("result") != "success":
        return "ci-evidence.lightweight-evidence-stale"
    if receipt.get("gitHead") != head:
        return "ci-evidence.lightweight-evidence-stale"
    registry = load_registry(root / REGISTRY_REL_PATH)
    doc_state = compute_documentation_state(root, registry)
    if receipt.get("documentationDigest") != doc_state.digest:
        return "ci-evidence.lightweight-evidence-stale"
    return None


def _validate_common_payload(
    root: Path,
    payload: dict[str, object],
    *,
    head: str,
    digest: str,
    run_id: str,
    format_json: bool,
) -> tuple[int, dict[str, object]] | None:
    if payload.get("mode") != "full":
        return _reject(
            "ci-evidence.not-full",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if payload.get("result") != "success" or payload.get("exitCode") != 0:
        return _reject(
            "ci-evidence.not-success",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if not payload.get("finalEvidence"):
        return _reject(
            "ci-evidence.not-final",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    tree_stable = payload.get("treeStable")
    digest_before = payload.get("treeDigestBefore")
    digest_after = payload.get("treeDigestAfter")
    if not tree_stable:
        return _reject(
            "ci-evidence.tree-unstable",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if not isinstance(digest_before, str) or not isinstance(digest_after, str):
        return _reject(
            "ci-evidence.schema",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if digest_before != digest_after:
        return _reject(
            "ci-evidence.tree-unstable",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    summary_branch = payload.get("gitBranch")
    summary_detached = payload.get("gitDetached")
    if summary_branch != git_branch(root):
        return _reject(
            "ci-evidence.branch-mismatch",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if summary_detached != git_detached(root):
        return _reject(
            "ci-evidence.branch-mismatch",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    checks = payload.get("checks")
    if not isinstance(checks, list):
        return _reject(
            "ci-evidence.schema",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    for item in checks:
        if isinstance(item, dict) and item.get("status") == "failed":
            return _reject(
                "ci-evidence.check-failed",
                head=head,
                digest=digest,
                run_id=run_id,
                format_json=format_json,
            )
    if payload.get("failedCheckId"):
        return _reject(
            "ci-evidence.check-failed",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    history_at = payload.get("historyAtCompletion")
    if not isinstance(history_at, dict):
        return _reject(
            "ci-evidence.history-invalid",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    attempts = history_at.get("fullCiAttempts")
    failures = history_at.get("fullCiFailures")
    successes = history_at.get("fullCiSuccesses")
    if not all(isinstance(value, int) for value in (attempts, failures, successes)):
        return _reject(
            "ci-evidence.history-invalid",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if attempts != failures + successes or successes < 1:
        return _reject(
            "ci-evidence.history-invalid",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    artifacts = root / ".artifacts" / "ci"
    recomputed = summarize_ci_history(artifacts)
    if (
        recomputed.full_ci_attempts != attempts
        or recomputed.full_ci_failures != failures
        or recomputed.full_ci_successes != successes
    ):
        return _reject(
            "ci-evidence.history-invalid",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    return None


def verify_ci_evidence(
    root: Path,
    summary_path: Path | None = None,
    *,
    format_json: bool = False,
    release: bool = False,
    paths: EnvironmentPaths | None = None,
) -> tuple[int, dict[str, object]]:
    env_paths = paths or production_environment_paths(root)
    summary = summary_path or env_paths.ci_summary_path
    head = git_head(root)
    digest = content_tree_digest(root)
    registry = load_registry(root / REGISTRY_REL_PATH)
    current_ci_input = compute_ci_input_state(root, registry)

    unknown_paths = [
        path
        for path in changed_source_paths(root)
        if not is_digest_excluded(path)
        and not is_excluded_path(path, registry)
        and classify_path(path, registry) == ChangeClass.UNKNOWN
    ]
    if unknown_paths:
        return _reject(
            "ci-evidence.unknown-change",
            head=head,
            digest=digest,
            format_json=format_json,
        )

    ci_dirty = changed_ci_input_paths(root, registry)
    if ci_dirty:
        return _reject(
            "ci-evidence.ci-input-mismatch",
            head=head,
            digest=digest,
            format_json=format_json,
        )

    if not summary.is_file():
        return _reject(
            "ci-evidence.missing",
            head=head,
            digest=digest,
            format_json=format_json,
        )

    try:
        payload = json.loads(summary.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return _reject(
            "ci-evidence.schema",
            head=head,
            digest=digest,
            format_json=format_json,
        )
    if not isinstance(payload, dict):
        return _reject(
            "ci-evidence.schema",
            head=head,
            digest=digest,
            format_json=format_json,
        )

    run_id = str(payload.get("runId", ""))
    schema = payload.get("schemaVersion")
    if schema not in SUPPORTED_SCHEMAS:
        return _reject(
            "ci-evidence.schema",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    common_failure = _validate_common_payload(
        root,
        payload,
        head=head,
        digest=digest,
        run_id=run_id,
        format_json=format_json,
    )
    if common_failure is not None:
        return common_failure

    environment_failure = _validate_environment_evidence(
        root, payload, head=head, env_paths=env_paths
    )
    if environment_failure:
        return _reject(
            environment_failure,
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    environment_failure = _validate_environment_identity(root, payload)
    if environment_failure:
        return _reject(
            environment_failure,
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    run_head = _summary_run_head(payload)
    if release and run_head != head:
        return _reject(
            "ci-evidence.head-mismatch",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
            match="release-exact-head-required",
        )

    summary_ci_input = payload.get("ciInputDigest")
    if schema >= 4:
        if not isinstance(summary_ci_input, str) or not summary_ci_input:
            return _reject(
                "ci-evidence.schema",
                head=head,
                digest=digest,
                run_id=run_id,
                format_json=format_json,
            )
        if summary_ci_input != current_ci_input.digest:
            return _reject(
                "ci-evidence.ci-input-mismatch",
                head=head,
                digest=digest,
                run_id=run_id,
                format_json=format_json,
            )

    if run_head == head:
        if schema < 4:
            summary_digest = payload.get("treeDigest")
            if summary_digest != digest:
                return _reject(
                    "ci-evidence.digest-mismatch",
                    head=head,
                    digest=digest,
                    run_id=run_id,
                    format_json=format_json,
                )
        if not is_working_tree_clean(root):
            return _reject(
                "ci-evidence.dirty-tree",
                head=head,
                digest=digest,
                run_id=run_id,
                format_json=format_json,
            )
        result = {
            "result": "success",
            "match": "exact-head",
            "gitHead": head,
            "treeDigest": digest,
            "ciInputDigest": current_ci_input.digest,
            "runId": run_id,
            "historyAtCompletion": payload.get("historyAtCompletion"),
        }
        if format_json:
            return 0, result
        _success(
            head=head,
            digest=digest,
            run_id=run_id,
            match="exact-head",
            ci_input_digest=current_ci_input.digest,
        )
        return 0, result

    if schema < 4 or release:
        return _reject(
            "ci-evidence.head-mismatch",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    verify = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{run_head}^{{commit}}"],
        check=False,
        capture_output=True,
    )
    if verify.returncode != 0:
        return _reject(
            "ci-evidence.run-head-unavailable",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    diff_paths = [
        path
        for path in _committed_diff_paths(root, run_head, head)
        if not is_digest_excluded(path) and not is_excluded_path(path, registry)
    ]
    for path in diff_paths:
        change_class = classify_path(path, registry)
        if change_class == ChangeClass.UNKNOWN:
            return _reject(
                "ci-evidence.unknown-change",
                head=head,
                digest=digest,
                run_id=run_id,
                format_json=format_json,
            )
        if change_class in FULL_CI_CHANGE_CLASSES:
            return _reject(
                "ci-evidence.disallowed-change-class",
                head=head,
                digest=digest,
                run_id=run_id,
                format_json=format_json,
            )

    lightweight_failure = _validate_lightweight_receipt(root, head, paths=env_paths)
    if lightweight_failure:
        return _reject(
            lightweight_failure,
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    result = {
        "result": "success",
        "match": "reused-non-ci-change",
        "gitHead": head,
        "gitHeadAtRun": run_head,
        "treeDigest": digest,
        "ciInputDigest": current_ci_input.digest,
        "runId": run_id,
        "historyAtCompletion": payload.get("historyAtCompletion"),
    }
    if format_json:
        return 0, result
    _success(
        head=head,
        digest=digest,
        run_id=run_id,
        match="reused-non-ci-change",
        run_head=run_head,
        ci_input_digest=current_ci_input.digest,
    )
    return 0, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify CI summary evidence.")
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / ".artifacts" / "ci" / "ci-summary.json",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Require exact Git HEAD match (release/publication workflows).",
    )
    args = parser.parse_args(argv)
    env_paths = production_environment_paths(ROOT)
    code, payload = verify_ci_evidence(
        ROOT,
        args.summary,
        format_json=args.format == "json",
        release=args.release,
        paths=env_paths,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
