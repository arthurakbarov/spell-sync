#!/usr/bin/env python3
"""Decide whether full CI is required for the current repository state."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_impact.constants import (  # noqa: E402
    NON_CI_CHANGE_CLASSES,
    ChangeClass,
)
from scripts.ci_impact.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    classify_path,
    classify_paths,
    is_excluded_path,
    load_registry,
    requires_full_ci,
)
from scripts.ci_input_state import changed_ci_input_paths, compute_ci_input_state  # noqa: E402
from scripts.environment_contract.paths import (  # noqa: E402
    EnvironmentPaths,
    production_environment_paths,
)
from scripts.test_selection.tree_state import (  # noqa: E402
    changed_source_paths,
    git_head,
    is_digest_excluded,
)

EVIDENCE_SCRIPT = Path(__file__).resolve().parent / "check_ci_evidence.py"


@dataclass(frozen=True, slots=True)
class NecessityResult:
    result: str
    reason: str
    classes: tuple[ChangeClass, ...] = ()
    changed_files: int = 0
    reusable_run_head: str = ""
    explanations: tuple[str, ...] = ()


def _git_diff_name_status(root: Path, base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "-z", f"{base}..{head}"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        return []
    return [
        item.decode("utf-8", errors="surrogateescape") for item in proc.stdout.split(b"\0") if item
    ]


def _load_summary(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _summary_ci_input_digest(summary: dict[str, object]) -> str | None:
    value = summary.get("ciInputDigest")
    return value if isinstance(value, str) and value else None


def _summary_run_head(summary: dict[str, object]) -> str:
    for key in ("gitHeadAtRun", "gitHead"):
        value = summary.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _current_evidence_valid(
    root: Path,
    summary: dict[str, object],
    *,
    paths: EnvironmentPaths,
) -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "scripts.check_ci_evidence",
        EVIDENCE_SCRIPT,
    )
    if not spec or not spec.loader:
        return False
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code, _payload = module.verify_ci_evidence(
        root,
        paths.ci_summary_path,
        format_json=True,
        paths=paths,
    )
    return code == 0


def _is_tracked_change_path(path: str, registry) -> bool:
    if is_digest_excluded(path) or is_excluded_path(path, registry):
        return False
    return True


def assess_ci_necessity(
    root: Path,
    *,
    base: str | None = None,
    explain: bool = False,
    purpose: str = "local",
    paths: EnvironmentPaths | None = None,
) -> NecessityResult:
    if purpose not in {"local", "publish"}:
        raise ValueError(f"unsupported purpose: {purpose!r} (expected local|publish)")
    env_paths = paths or production_environment_paths(root)
    registry = load_registry(root / REGISTRY_REL_PATH)
    head = git_head(root)
    current_input = compute_ci_input_state(root, registry)

    def _maybe_local_commit_gate(
        *,
        reason: str,
        classes: tuple[ChangeClass, ...] = (),
        changed_files: int = 0,
        explanations: tuple[str, ...] = (),
        reusable_run_head: str = "",
    ) -> NecessityResult:
        if purpose == "local":
            return NecessityResult(
                result="commit-gate-sufficient",
                reason=reason,
                classes=classes,
                changed_files=changed_files,
                reusable_run_head=reusable_run_head,
                explanations=explanations,
            )
        return NecessityResult(
            result="full-required",
            reason=reason,
            classes=classes,
            changed_files=changed_files,
            reusable_run_head=reusable_run_head,
            explanations=explanations,
        )

    uncommitted = changed_source_paths(root)
    unclassified = [
        path
        for path in uncommitted
        if _is_tracked_change_path(path, registry)
        and classify_path(path, registry) == ChangeClass.UNKNOWN
    ]
    if unclassified:
        mapping = classify_paths(unclassified, registry)
        explanations = tuple(f"{path} -> {mapping[path].value}" for path in sorted(mapping))
        return NecessityResult(
            result="full-required",
            reason="unknown-change",
            classes=(ChangeClass.UNKNOWN,),
            changed_files=len(unclassified),
            explanations=explanations if explain else (),
        )

    ci_dirty = changed_ci_input_paths(root, registry)
    if ci_dirty:
        class_set = {classify_path(path, registry) for path in ci_dirty}
        classes = tuple(sorted(class_set, key=lambda item: item.value))
        explanations = (
            tuple(f"{path} -> {classify_path(path, registry).value}" for path in ci_dirty)
            if explain
            else ()
        )
        return _maybe_local_commit_gate(
            reason="ci-input-dirty",
            classes=classes,
            changed_files=len(ci_dirty),
            explanations=explanations,
        )

    compare_base = base or _summary_run_head(_load_summary(env_paths.ci_summary_path) or {})
    diff_paths: list[str] = []
    if compare_base and compare_base != "unknown":
        verify = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{compare_base}^{{commit}}"],
            check=False,
            capture_output=True,
        )
        if verify.returncode != 0:
            return _maybe_local_commit_gate(reason="run-head-unavailable")
        diff_paths = [
            path
            for path in _git_diff_name_status(root, compare_base, head)
            if _is_tracked_change_path(path, registry)
        ]

    if diff_paths:
        classes_set = {classify_path(path, registry) for path in diff_paths}
        if ChangeClass.UNKNOWN in classes_set:
            explanations = (
                tuple(f"{path} -> {classify_path(path, registry).value}" for path in diff_paths)
                if explain
                else ()
            )
            return NecessityResult(
                result="full-required",
                reason="unknown-change",
                classes=(ChangeClass.UNKNOWN,),
                changed_files=len(diff_paths),
                explanations=explanations,
            )
        full_classes = tuple(
            sorted(
                (item for item in classes_set if requires_full_ci(item)),
                key=lambda item: item.value,
            )
        )
        if full_classes:
            explanations = (
                tuple(f"{path} -> {classify_path(path, registry).value}" for path in diff_paths)
                if explain
                else ()
            )
            return _maybe_local_commit_gate(
                reason="product-input-changed",
                classes=full_classes,
                changed_files=len(diff_paths),
                explanations=explanations,
            )

    summary = _load_summary(env_paths.ci_summary_path)
    if summary and _current_evidence_valid(root, summary, paths=env_paths):
        return NecessityResult(result="no-action", reason="current-evidence-valid")

    if summary and summary.get("result") == "success" and summary.get("finalEvidence"):
        summary_digest = _summary_ci_input_digest(summary)
        run_head = _summary_run_head(summary)
        if summary_digest and summary_digest == current_input.digest and run_head:
            non_ci_only = all(
                classify_path(path, registry) in NON_CI_CHANGE_CLASSES for path in diff_paths
            )
            if non_ci_only:
                diff_class_set = {classify_path(path, registry) for path in diff_paths}
                return NecessityResult(
                    result="lightweight-sufficient",
                    reason="non-ci-inputs-only",
                    classes=tuple(sorted(diff_class_set, key=lambda item: item.value)),
                    changed_files=len(diff_paths),
                    reusable_run_head=run_head,
                )

    if not summary or summary.get("result") != "success":
        return _maybe_local_commit_gate(reason="missing-valid-evidence")

    return _maybe_local_commit_gate(reason="ci-input-mismatch")


def _print_text(result: NecessityResult) -> None:
    print(f"CI_NECESSITY_RESULT={result.result}")
    print(f"CI_NECESSITY_REASON={result.reason}")
    if result.classes:
        print(f"CI_NECESSITY_CLASSES={','.join(item.value for item in result.classes)}")
    if result.changed_files:
        print(f"CI_NECESSITY_CHANGED_FILES={result.changed_files}")
    if result.reusable_run_head:
        print(f"CI_NECESSITY_REUSABLE_RUN_HEAD={result.reusable_run_head}")
    for line in result.explanations:
        print(f"CI_NECESSITY_FILE={line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess whether full CI is required.")
    parser.add_argument("--base", help="Compare committed changes from this git HEAD")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument(
        "--purpose",
        choices=("local", "publish"),
        default="local",
        help="local: commit-gate for product changes; publish: full CI when inputs change",
    )
    args = parser.parse_args(argv)
    result = assess_ci_necessity(
        ROOT,
        base=args.base,
        explain=args.explain,
        purpose=args.purpose,
    )
    if args.format == "json":
        print(
            json.dumps(
                {
                    "result": result.result,
                    "reason": result.reason,
                    "purpose": args.purpose,
                    "classes": [item.value for item in result.classes],
                    "changedFiles": result.changed_files,
                    "reusableRunHead": result.reusable_run_head,
                    "explanations": list(result.explanations),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"CI_NECESSITY_PURPOSE={args.purpose}")
        _print_text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
