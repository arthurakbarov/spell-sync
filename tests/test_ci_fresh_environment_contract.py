"""GitHub workflow binds full CI to canonical environment contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_full_ci_job_uses_canonical_python_and_project_environment_sync() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "full-ci" in text
    assert 'python-version: "3.12.13"' in text
    assert "scripts/project_environment.py sync" in text


def test_full_ci_gate_runs_ci_runner_without_uv_sync() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    full_ci_start = text.index("Full CI")
    full_ci_block = text[full_ci_start : full_ci_start + 400]
    assert "scripts/ci_runner.py" in full_ci_block
    assert "uv sync" not in full_ci_block
