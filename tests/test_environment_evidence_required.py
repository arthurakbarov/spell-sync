"""Environment evidence is required for CI evidence verification."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.environment_contract import paths as environment_paths_module
from scripts.environment_contract.evidence import write_environment_evidence
from scripts.environment_contract.fingerprint import resolve_project_environment_fingerprint
from scripts.project_environment import cmd_sync

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _uv_version() -> str:
    import re

    proc = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False)
    match = re.search(r"uv\s+(\d+\.\d+\.\d+)", proc.stdout)
    return match.group(1) if match else ""


def _load_evidence_mod():
    spec = importlib.util.spec_from_file_location(
        "scripts.check_ci_evidence",
        ROOT / "scripts" / "check-ci-evidence.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_environment_inputs(dest: Path) -> None:
    for name in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "config", dest / "config")


@pytest.fixture(scope="module")
def synced_repo_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("uv") is None:
        pytest.skip("uv required for environment evidence tests")
    repo = tmp_path_factory.mktemp("environment-evidence-template")
    _copy_environment_inputs(repo)
    sync = cmd_sync(repo, allow_python_download=False)
    if sync.exit_code != 0 and sync.failed_id == "environment.sync-required":
        pytest.skip(f"uv sync unavailable: {sync.message}")
    assert sync.exit_code == 0
    return repo


def _init_git(repo: Path) -> str:
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
    (repo / "ci").mkdir(exist_ok=True)
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "add",
            "tracked.txt",
            "ci/ci-impact.toml",
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            "config",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True
    )
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _write_valid_summary(repo: Path, paths, head: str) -> None:
    fingerprint = resolve_project_environment_fingerprint(repo, uv_version=_uv_version())
    assert fingerprint is not None
    payload = {
        "schemaVersion": 5,
        "runId": "test-run",
        "result": "success",
        "exitCode": 0,
        "mode": "full",
        "finalEvidence": True,
        "gitHeadAtRun": head,
        "gitHead": head,
        "gitBranch": "main",
        "gitDetached": False,
        "treeDigestBefore": "a" * 64,
        "treeDigestAfter": "a" * 64,
        "treeStable": True,
        "ciInputDigest": "b" * 64,
        "ciInputDigestBefore": "b" * 64,
        "ciInputDigestAfter": "b" * 64,
        "ciInputStable": True,
        "environmentFingerprint": fingerprint.signature(),
        "environmentFingerprintBefore": fingerprint.signature(),
        "environmentFingerprintAfter": fingerprint.signature(),
        "environmentStable": True,
        "environmentContractDigest": fingerprint.environment_contract_digest,
        "pyprojectDigest": fingerprint.pyproject_digest,
        "uvLockDigest": fingerprint.uv_lock_digest,
        "installedEnvironmentDigest": fingerprint.installed_environment_digest,
        "pythonVersion": fingerprint.python_version,
        "pythonImplementation": fingerprint.python_implementation,
        "pythonCacheTag": fingerprint.python_cache_tag,
        "uvVersion": fingerprint.uv_version,
        "selectedDependencyGroups": list(fingerprint.selected_dependency_groups),
        "checks": [],
        "historyAtCompletion": {"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1},
    }
    paths.ci_summary_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ci_summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_missing_environment_evidence_rejected_with_venv_intact(
    synced_repo_template: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(synced_repo_template, repo, symlinks=True)
    head = _init_git(repo)
    paths = environment_paths_module.test_environment_paths(tmp_path / "home", project_root=repo)
    fingerprint = resolve_project_environment_fingerprint(repo, uv_version=_uv_version())
    assert fingerprint is not None
    write_environment_evidence(
        repo,
        fingerprint=fingerprint,
        repository_head=head,
        check_exit=0,
        lock_exit=0,
        paths=paths,
    )
    _write_valid_summary(repo, paths, head)
    evidence_path = paths.environment_evidence_path
    assert evidence_path.is_file()
    evidence_path.unlink()
    assert (repo / ".venv").is_dir()

    mod = _load_evidence_mod()
    payload = json.loads(paths.ci_summary_path.read_text(encoding="utf-8"))
    failed = mod._validate_environment_evidence(repo, payload, head=head, env_paths=paths)
    assert failed == "ci-evidence.environment-mismatch"


def test_environment_evidence_rejected_when_venv_missing(
    synced_repo_template: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(synced_repo_template, repo, symlinks=True)
    head = _init_git(repo)
    paths = environment_paths_module.test_environment_paths(tmp_path / "home", project_root=repo)
    fingerprint = resolve_project_environment_fingerprint(repo, uv_version=_uv_version())
    assert fingerprint is not None
    write_environment_evidence(
        repo,
        fingerprint=fingerprint,
        repository_head=head,
        check_exit=0,
        lock_exit=0,
        paths=paths,
    )
    _write_valid_summary(repo, paths, head)
    shutil.rmtree(repo / ".venv")

    mod = _load_evidence_mod()
    payload = json.loads(paths.ci_summary_path.read_text(encoding="utf-8"))
    failed = mod._validate_environment_evidence(repo, payload, head=head, env_paths=paths)
    assert failed == "ci-evidence.environment-mismatch"
