"""EnvironmentPaths integration with CI necessity assessment."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from scripts.environment_contract import paths as environment_paths_module

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_necessity_mod():
    spec = importlib.util.spec_from_file_location(
        "scripts.check_ci_necessity",
        ROOT / "scripts" / "check-ci-necessity.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def assess_ci_necessity(*args, **kwargs):
    return _load_necessity_mod().assess_ci_necessity(*args, **kwargs)


def test_production_paths_reference_repository_artifact_roots() -> None:
    artifact_root = ROOT / ".artifacts"
    assert (artifact_root / "ci" / "ci-summary.json") == artifact_root / "ci" / "ci-summary.json"
    assert (artifact_root / "environment" / "environment.json") == (
        artifact_root / "environment" / "environment.json"
    )
    assert artifact_root.is_dir() or not (artifact_root / "ci" / "ci-summary.json").exists()


def test_assess_ci_necessity_requires_full_ci_when_temp_paths_have_no_summary(
    tmp_path: Path,
) -> None:
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
    assert not temp_paths.ci_summary_path.is_file()

    result = assess_ci_necessity(repo, paths=temp_paths)
    assert result.result == "full-required"
    assert result.result != "no-action"
    assert result.reason in {"missing-valid-evidence", "run-head-unavailable", "ci-input-mismatch"}
