"""Unit tests for tiered publish coverage policy."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.coverage_policy import (
    BRANCH_MINIMUM_PERCENT,
    PRESENTATION_LINE_PERCENT,
    STRICT_LINE_PERCENT,
    classify_tier,
    evaluate_coverage_json,
    evaluate_coverage_payload,
)


def _file(
    *,
    statements: int,
    covered: int,
    branches: int = 0,
    covered_branches: int = 0,
) -> dict[str, object]:
    return {
        "summary": {
            "num_statements": statements,
            "covered_lines": covered,
            "missing_lines": statements - covered,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


def test_classify_tiers() -> None:
    assert classify_tier("spell_sync/application/service.py") == "strict"
    assert classify_tier("spell_sync/push_journal.py") == "strict"
    assert classify_tier("spell_sync/project_setup/execute.py") == "strict"
    assert classify_tier("spell_sync/tui/controller.py") == "presentation"
    assert classify_tier("spell_sync/push_render.py") == "presentation"
    assert classify_tier("spell_sync/words.py") == "remainder"


def test_strict_requires_full_lines(tmp_path: Path) -> None:
    payload = {
        "files": {
            "spell_sync/application/service.py": _file(statements=100, covered=99),
            "spell_sync/tui/app.py": _file(statements=100, covered=98),
        }
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    code, message = evaluate_coverage_json(path)
    assert code == 1
    assert "application/service.py" in message
    assert "tui/app.py" not in message


def test_presentation_allows_ninety_eight() -> None:
    payload = {
        "files": {
            "spell_sync/tui/app.py": _file(
                statements=100,
                covered=98,
                branches=50,
                covered_branches=48,
            ),
            "spell_sync/words.py": _file(
                statements=100,
                covered=98,
                branches=10,
                covered_branches=10,
            ),
        }
    }
    verdicts = evaluate_coverage_payload(payload)
    assert all(item.ok for item in verdicts)
    assert STRICT_LINE_PERCENT == 100
    assert PRESENTATION_LINE_PERCENT == 98
    assert BRANCH_MINIMUM_PERCENT == 96


def test_branch_floor_applies_to_all_tiers(tmp_path: Path) -> None:
    payload = {
        "files": {
            "spell_sync/words.py": _file(
                statements=10,
                covered=10,
                branches=100,
                covered_branches=95,
            )
        }
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    code, message = evaluate_coverage_json(path)
    assert code == 1
    assert "branches" in message
