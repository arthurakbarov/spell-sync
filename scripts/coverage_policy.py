#!/usr/bin/env python3
"""Publish CI coverage policy: strict core vs presentation/remainder tiers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

STRICT_LINE_PERCENT = 100
PRESENTATION_LINE_PERCENT = 98
BRANCH_MINIMUM_PERCENT = 90

# application/ + mutation / recovery / project-setup write paths
STRICT_PREFIXES: tuple[str, ...] = (
    "spell_sync/application/",
    "spell_sync/project_setup/",
)
STRICT_FILES: frozenset[str] = frozenset(
    {
        "spell_sync/journal_schema.py",
        "spell_sync/mutation_guards.py",
        "spell_sync/operation_lock.py",
        "spell_sync/push_abort.py",
        "spell_sync/push_journal.py",
        "spell_sync/push_plan.py",
        "spell_sync/push_prepared.py",
        "spell_sync/push_setup.py",
        "spell_sync/push_transaction.py",
        "spell_sync/recover_cmd.py",
        "spell_sync/removal_review.py",
        "spell_sync/secure_artifacts.py",
        "spell_sync/sync_run.py",
        "spell_sync/trusted_internal_fs.py",
    }
)

# TUI and human-facing rendering — soft line floor
PRESENTATION_PREFIXES: tuple[str, ...] = ("spell_sync/tui/",)
PRESENTATION_FILES: frozenset[str] = frozenset(
    {
        "spell_sync/json_output.py",
        "spell_sync/log.py",
        "spell_sync/operation_reports.py",
        "spell_sync/push_render.py",
    }
)


@dataclass(frozen=True, slots=True)
class FileVerdict:
    path: str
    tier: str
    line_percent: float
    branch_percent: float
    line_required: float
    branch_required: float
    ok: bool
    detail: str


def _normalize_path(raw: str) -> str:
    path = raw.replace("\\", "/")
    marker = "spell_sync/"
    if marker in path:
        return path[path.index(marker) :]
    return path


def classify_tier(path: str) -> str:
    normalized = _normalize_path(path)
    if normalized in STRICT_FILES or any(normalized.startswith(p) for p in STRICT_PREFIXES):
        return "strict"
    if normalized in PRESENTATION_FILES or any(
        normalized.startswith(p) for p in PRESENTATION_PREFIXES
    ):
        return "presentation"
    return "remainder"


def _line_required(tier: str) -> float:
    if tier == "strict":
        return float(STRICT_LINE_PERCENT)
    return float(PRESENTATION_LINE_PERCENT)


def _percent(covered: float, total: float) -> float:
    if total <= 0:
        return 100.0
    return 100.0 * covered / total


def evaluate_coverage_payload(payload: dict[str, object]) -> list[FileVerdict]:
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("coverage.json missing files map")

    verdicts: list[FileVerdict] = []
    for raw_path, entry in sorted(files.items()):
        if not isinstance(entry, dict):
            raise ValueError(f"malformed coverage entry for {raw_path}")
        summary = entry.get("summary")
        if not isinstance(summary, dict):
            raise ValueError(f"coverage entry missing summary for {raw_path}")
        path = _normalize_path(str(raw_path))
        if not path.startswith("spell_sync/"):
            continue
        tier = classify_tier(path)
        statements = float(summary.get("num_statements") or 0)
        covered_lines = float(summary.get("covered_lines") or 0)
        branches = float(summary.get("num_branches") or 0)
        covered_branches = float(summary.get("covered_branches") or 0)
        line_pct = _percent(covered_lines, statements)
        branch_pct = _percent(covered_branches, branches)
        line_req = _line_required(tier)
        # Branch floor applies to strict (application/mutation) paths only. Presentation and
        # remainder keep line tiers; Textual exit BrParts otherwise trip a global 96% floor
        # even when lines are complete.
        branch_req = float(BRANCH_MINIMUM_PERCENT) if tier == "strict" else 0.0
        problems: list[str] = []
        if line_pct + 1e-9 < line_req:
            missing = int(summary.get("missing_lines") or (statements - covered_lines))
            problems.append(f"lines {line_pct:.2f}% < {line_req:g}% ({missing} missing)")
        if branch_req > 0 and branch_pct + 1e-9 < branch_req:
            problems.append(f"branches {branch_pct:.2f}% < {branch_req:g}%")
        verdicts.append(
            FileVerdict(
                path=path,
                tier=tier,
                line_percent=line_pct,
                branch_percent=branch_pct,
                line_required=line_req,
                branch_required=branch_req,
                ok=not problems,
                detail="; ".join(problems),
            )
        )
    if not verdicts:
        raise ValueError("no spell_sync package files evaluated")
    return verdicts


def evaluate_coverage_json(path: Path) -> tuple[int, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 1, f"coverage policy: unreadable coverage.json ({exc})"
    if not isinstance(payload, dict):
        return 1, "coverage policy: coverage.json root must be an object"
    try:
        verdicts = evaluate_coverage_payload(payload)
    except ValueError as exc:
        return 1, f"coverage policy: {exc}"
    failures = [item for item in verdicts if not item.ok]
    if failures:
        lines = ["coverage policy: failed"]
        for item in failures[:40]:
            lines.append(f"  [{item.tier}] {item.path}: {item.detail}")
        if len(failures) > 40:
            lines.append(f"  ... and {len(failures) - 40} more")
        return 1, "\n".join(lines)

    by_tier: dict[str, int] = {}
    for item in verdicts:
        by_tier[item.tier] = by_tier.get(item.tier, 0) + 1
    summary = ", ".join(f"{name}={count}" for name, count in sorted(by_tier.items()))
    return (
        0,
        "coverage policy: ok "
        f"(strict={STRICT_LINE_PERCENT}% lines / ≥{BRANCH_MINIMUM_PERCENT}% branches, "
        f"presentation/remainder≥{PRESENTATION_LINE_PERCENT}% lines; files: {summary})",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=Path("coverage.json"),
        help="Path to coverage.py JSON report",
    )
    args = parser.parse_args(argv)
    code, message = evaluate_coverage_json(args.coverage_json)
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
