"""CI evidence rejects forged environment identity fields."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.environment_contract import paths as environment_paths_module
from scripts.environment_contract.probe import venv_python

ROOT = Path(__file__).resolve().parents[1]


def _uv_version() -> str:
    proc = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False)
    match = re.search(r"uv\s+(\d+\.\d+\.\d+)", proc.stdout)
    return match.group(1) if match else ""


def _load_evidence_module():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "scripts.check_ci_evidence",
        ROOT / "scripts" / "check-ci-evidence.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evidence_mod():
    return _load_evidence_module()


def _copy_environment_inputs(dest: Path) -> None:
    for name in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "config", dest / "config")


def _install_registry(repo: Path) -> None:
    (repo / "ci").mkdir(parents=True, exist_ok=True)
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _init_git_repo(repo: Path) -> str:
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
    (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _install_registry(repo)
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


@pytest.fixture(scope="module")
def synced_git_repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, object]:
    if shutil.which("uv") is None:
        pytest.skip("uv required for environment CI evidence tests")
    tmp_path = tmp_path_factory.mktemp("environment-ci-evidence")
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_environment_inputs(repo)
    _init_git_repo(repo)
    from scripts.project_environment import cmd_sync

    sync = cmd_sync(repo, allow_python_download=False)
    if sync.exit_code != 0 and sync.failed_id == "environment.sync-required":
        pytest.skip(f"uv sync unavailable in test sandbox: {sync.message}")
    assert sync.exit_code == 0, f"{sync.failed_id}: {sync.message}"
    paths = environment_paths_module.test_environment_paths(tmp_path / "home", project_root=repo)
    return repo, paths


def _build_summary(repo: Path, paths, *, head: str) -> dict[str, object]:
    from scripts.ci_history import summarize_ci_history
    from scripts.ci_impact.registry import load_registry
    from scripts.ci_input_state import compute_ci_input_state
    from scripts.environment_contract.fingerprint import resolve_project_environment_fingerprint
    from scripts.test_selection.tree_state import content_tree_digest, git_branch, git_detached

    registry = load_registry(repo / "ci" / "ci-impact.toml")
    ci_input = compute_ci_input_state(repo, registry)
    digest = content_tree_digest(repo)
    fingerprint = resolve_project_environment_fingerprint(repo, uv_version=_uv_version())
    assert fingerprint is not None
    env_summary = fingerprint.to_summary_dict()
    run_id = "env-evidence-test"
    history = {"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1}
    payload: dict[str, object] = {
        "schemaVersion": 5,
        "runId": run_id,
        "result": "success",
        "exitCode": 0,
        "mode": "full",
        "finalEvidence": True,
        "gitHeadAtRun": head,
        "gitHead": head,
        "gitBranch": git_branch(repo),
        "gitDetached": git_detached(repo),
        "repositoryTreeDigest": digest,
        "treeDigest": digest,
        "treeDigestBefore": digest,
        "treeDigestAfter": digest,
        "treeStable": True,
        "ciInputDigest": ci_input.digest,
        "ciImpactSchemaVersion": 1,
        "evidenceScope": "full-ci-inputs",
        "reusableAcrossNonCiCommits": True,
        "historyAtCompletion": history,
        "fullCiAttempts": history["fullCiAttempts"],
        "fullCiFailures": history["fullCiFailures"],
        "fullCiSuccesses": history["fullCiSuccesses"],
        "checks": [{"id": "tests.pytest", "status": "passed", "exitCode": 0}],
        **env_summary,
    }
    paths.ci_summary_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ci_summary_path.write_text(json.dumps(payload), encoding="utf-8")
    artifacts = repo / ".artifacts" / "ci"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / f"ci-summary-{run_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    (artifacts / f"ci-run-{run_id}.log").write_text("ok\n", encoding="utf-8")
    summarize_ci_history(artifacts)
    return payload


@pytest.mark.parametrize(
    "field,value",
    (
        ("environmentFingerprint", "0" * 64),
        ("installedEnvironmentDigest", "1" * 64),
        ("pythonVersion", "3.11.0"),
    ),
)
def test_verify_rejects_mutated_environment_summary_fields(
    evidence_mod,
    synced_git_repo: tuple[Path, object],
    field: str,
    value: str,
) -> None:
    repo, paths = synced_git_repo
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    payload = _build_summary(repo, paths, head=head)
    payload[field] = value
    paths.ci_summary_path.write_text(json.dumps(payload), encoding="utf-8")

    code, result = evidence_mod.verify_ci_evidence(repo, paths=paths, format_json=True)
    assert code == 1
    assert result.get("failedId") == "ci-evidence.environment-mismatch"


def test_verify_rejects_schema_v5_without_environment_fingerprint(
    evidence_mod,
    synced_git_repo: tuple[Path, object],
) -> None:
    repo, paths = synced_git_repo
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    payload = _build_summary(repo, paths, head=head)
    payload.pop("environmentFingerprint", None)
    paths.ci_summary_path.write_text(json.dumps(payload), encoding="utf-8")

    code, result = evidence_mod.verify_ci_evidence(repo, paths=paths, format_json=True)
    assert code == 1
    assert result.get("failedId") == "ci-evidence.environment-mismatch"


def test_verify_rejects_when_environment_evidence_file_missing(
    evidence_mod,
    synced_git_repo: tuple[Path, object],
) -> None:
    repo, paths = synced_git_repo
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    _build_summary(repo, paths, head=head)
    evidence_path = paths.environment_evidence_path
    if evidence_path.is_file():
        evidence_path.unlink()

    venv_py = venv_python(repo / ".venv")
    assert venv_py is not None
    venv_py.unlink()

    code, result = evidence_mod.verify_ci_evidence(repo, paths=paths, format_json=True)
    assert code == 1
    assert result.get("failedId") == "ci-evidence.environment-mismatch"
