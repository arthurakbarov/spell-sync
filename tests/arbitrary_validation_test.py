"""Arbitrary test module name uses temporary evidence paths when injected."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.environment_contract import paths as environment_paths_module

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_environment_generic_path_injection import _load_necessity_mod  # noqa: E402


def test_arbitrary_module_name_uses_temporary_evidence_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (repo / "ci").mkdir()
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "tracked.txt", "ci/ci-impact.toml"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True
    )

    temp_paths = environment_paths_module.test_environment_paths(
        tmp_path / "home", project_root=repo
    )
    result = _load_necessity_mod().assess_ci_necessity(repo, paths=temp_paths)
    assert result.result == "full-required"
    assert not temp_paths.ci_summary_path.exists()
