"""Residual ID disambiguation: R-PWR vs R-DUR."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mutation_safety_uses_r_dur_for_power_loss() -> None:
    text = (ROOT / "docs/architecture/MUTATION_SAFETY.md").read_text(encoding="utf-8")
    assert "R-DUR" in text
    assert "R-PWR" not in text
    assert "power-loss" in text.lower()


def test_roadmap_assigns_distinct_residual_meanings() -> None:
    roadmap = (ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8")
    assert "| R-PWR |" in roadmap
    assert "| R-DUR |" in roadmap
    pwr_lines = [line for line in roadmap.splitlines() if "| R-PWR |" in line]
    dur_lines = [line for line in roadmap.splitlines() if "| R-DUR |" in line]
    assert pwr_lines and "coverage-padding" in pwr_lines[0]
    assert dur_lines and "power-loss" in dur_lines[0].lower()


def test_no_single_line_binds_r_pwr_to_power_loss() -> None:
    ambiguous: list[str] = []
    for path in (ROOT / "docs").rglob("*.md"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "R-PWR" not in line:
                continue
            if "power-loss" not in line.lower() and "power loss" not in line.lower():
                continue
            # Disambiguation sentences may mention both IDs.
            if "R-DUR" in line or "unrelated" in line.lower():
                continue
            ambiguous.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()}")
    assert ambiguous == []
