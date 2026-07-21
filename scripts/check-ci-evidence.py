#!/usr/bin/env python3
"""Verify that CI summary evidence matches the current committed repository state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_history import summarize_ci_history  # noqa: E402
from scripts.test_selection.tree_state import (  # noqa: E402
    content_tree_digest,
    git_branch,
    git_detached,
    git_head,
    is_working_tree_clean,
)

SUPPORTED_SCHEMAS = frozenset({3})


def _fail(failed_id: str, *, head: str = "", digest: str = "", run_id: str = "") -> int:
    print("CI_EVIDENCE_RESULT=failed")
    print(f"CI_EVIDENCE_FAILED_ID={failed_id}")
    if head:
        print(f"CI_EVIDENCE_HEAD={head}")
    if digest:
        print(f"CI_EVIDENCE_TREE_DIGEST={digest}")
    if run_id:
        print(f"CI_EVIDENCE_RUN_ID={run_id}")
    return 1


def _success(*, head: str, digest: str, run_id: str) -> int:
    print("CI_EVIDENCE_RESULT=success")
    print(f"CI_EVIDENCE_HEAD={head}")
    print(f"CI_EVIDENCE_TREE_DIGEST={digest}")
    print(f"CI_EVIDENCE_RUN_ID={run_id}")
    return 0


def _failure_result(
    failed_id: str,
    *,
    head: str,
    digest: str,
    run_id: str = "",
) -> dict[str, object]:
    result: dict[str, object] = {
        "result": "failed",
        "failedId": failed_id,
        "gitHead": head,
        "treeDigest": digest,
    }
    if run_id:
        result["runId"] = run_id
    return result


def _reject(
    failed_id: str,
    *,
    head: str,
    digest: str,
    run_id: str = "",
    format_json: bool,
) -> tuple[int, dict[str, object]]:
    result = _failure_result(failed_id, head=head, digest=digest, run_id=run_id)
    if not format_json:
        _fail(failed_id, head=head, digest=digest, run_id=run_id)
    return 1, result


def verify_ci_evidence(
    root: Path,
    summary_path: Path,
    *,
    format_json: bool = False,
) -> tuple[int, dict[str, object]]:
    head = git_head(root)
    digest = content_tree_digest(root)
    if not summary_path.is_file():
        return _reject(
            "ci-evidence.missing",
            head=head,
            digest=digest,
            format_json=format_json,
        )

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
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
    summary_digest = payload.get("treeDigest")
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
    if summary_digest != digest or summary_digest != digest_after:
        return _reject(
            "ci-evidence.digest-mismatch",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    summary_head = payload.get("gitHead")
    if summary_head != head:
        return _reject(
            "ci-evidence.head-mismatch",
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

    if not is_working_tree_clean(root):
        return _reject(
            "ci-evidence.dirty-tree",
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
    if attempts != failures + successes:
        return _reject(
            "ci-evidence.history-invalid",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )
    if successes < 1:
        return _reject(
            "ci-evidence.history-invalid",
            head=head,
            digest=digest,
            run_id=run_id,
            format_json=format_json,
        )

    top_attempts = payload.get("fullCiAttempts")
    top_failures = payload.get("fullCiFailures")
    top_successes = payload.get("fullCiSuccesses")
    if (top_attempts, top_failures, top_successes) != (attempts, failures, successes):
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

    result = {
        "result": "success",
        "gitHead": head,
        "treeDigest": digest,
        "runId": run_id,
        "historyAtCompletion": history_at,
    }
    if format_json:
        return 0, result
    _success(head=head, digest=digest, run_id=run_id)
    return 0, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify CI summary matches current HEAD.")
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / ".artifacts" / "ci" / "ci-summary.json",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    code, payload = verify_ci_evidence(ROOT, args.summary, format_json=args.format == "json")
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
