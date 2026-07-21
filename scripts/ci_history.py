"""Pure CI history aggregation from immutable summary artifacts."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CiHistoryCounts:
    full_ci_attempts: int
    full_ci_failures: int
    full_ci_successes: int

    def to_json_dict(self) -> dict[str, int]:
        return {
            "fullCiAttempts": self.full_ci_attempts,
            "fullCiFailures": self.full_ci_failures,
            "fullCiSuccesses": self.full_ci_successes,
        }

    def validate_invariant(self) -> bool:
        return self.full_ci_attempts == self.full_ci_failures + self.full_ci_successes


def _emit_warning(message: str, *, warnings: list[str] | None) -> None:
    if warnings is not None:
        warnings.append(message)
    else:
        print(message, file=sys.stderr)


def _is_full_success(payload: dict[str, object]) -> bool:
    return payload.get("result") == "success" and payload.get("exitCode") == 0


def summarize_ci_history(
    artifacts: Path,
    *,
    warnings: list[str] | None = None,
) -> CiHistoryCounts:
    """Count full CI runs from retained summary files; do not trust embedded counters."""
    attempts = failures = successes = 0
    if not artifacts.is_dir():
        return CiHistoryCounts(0, 0, 0)

    for path in sorted(artifacts.glob("ci-summary-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _emit_warning(
                f"ci-history: ignore malformed summary {path.name}: {exc}", warnings=warnings
            )
            continue
        if not isinstance(payload, dict):
            _emit_warning(f"ci-history: ignore non-object summary {path.name}", warnings=warnings)
            continue
        if payload.get("mode") != "full":
            continue
        attempts += 1
        if _is_full_success(payload):
            successes += 1
        else:
            failures += 1

    counts = CiHistoryCounts(attempts, failures, successes)
    if not counts.validate_invariant():
        _emit_warning(
            "ci-history: invariant violated: attempts != failures + successes",
            warnings=warnings,
        )
    return counts
