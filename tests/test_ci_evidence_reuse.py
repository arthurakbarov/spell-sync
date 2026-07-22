#!/usr/bin/env python3
"""Tests for reusable CI evidence verification."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.environment_contract.evidence import write_environment_evidence
from scripts.environment_contract.fingerprint import resolve_project_environment_fingerprint
from scripts.project_environment import cmd_sync


def _uv_version() -> str:
    proc = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False)
    match = re.search(r"uv\s+(\d+\.\d+\.\d+)", proc.stdout)
    return match.group(1) if match else ""


@pytest.fixture(scope="module")
def synced_environment_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("uv") is None:
        pytest.skip("uv required for CI evidence reuse tests")
    repo = tmp_path_factory.mktemp("ci-evidence-reuse-template")
    _copy_environment_inputs(repo)
    sync = cmd_sync(repo, allow_python_download=False)
    if sync.exit_code != 0 and sync.failed_id == "environment.sync-required":
        pytest.skip(f"uv sync unavailable: {sync.message}")
    assert sync.exit_code == 0
    return repo


def _copy_environment_inputs(dest: Path) -> None:
    for name in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "config", dest / "config")


def _load_evidence_mod():
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
    return _load_evidence_mod()


def _clone_environment_repo(template: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(template, dest)
    git_dir = dest / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    _init_git(dest)
    (dest / "ci").mkdir(exist_ok=True)
    (dest / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (dest / "spell_sync").mkdir(exist_ok=True)
    (dest / "spell_sync" / "sample.py").write_text("x = 1\n", encoding="utf-8")
    _git_add_all(dest)
    _git_commit(dest, "base")
    return dest


def _init_repo_with_product(tmp_path: Path, template: Path) -> Path:
    return _clone_environment_repo(template, tmp_path / "repo")


def _init_repo_with_docs(tmp_path: Path, template: Path) -> Path:
    repo = _init_repo_with_product(tmp_path, template)
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("hello\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "docs seed")
    return repo


def _environment_fingerprint(repo: Path):
    fingerprint = resolve_project_environment_fingerprint(repo, uv_version=_uv_version())
    if fingerprint is None:
        pytest.fail("environment fingerprint unavailable for CI evidence reuse test repo")
    return fingerprint


def _write_environment_evidence_for_head(repo: Path) -> None:
    head = _git_head(repo)
    fingerprint = _environment_fingerprint(repo)
    write_environment_evidence(
        repo,
        fingerprint=fingerprint,
        repository_head=head,
        check_exit=0,
        lock_exit=0,
    )


def test_reused_non_ci_change_with_lightweight_receipt(
    evidence_mod, synced_environment_template: Path, tmp_path: Path
) -> None:
    repo = _init_repo_with_docs(tmp_path, synced_environment_template)
    run_head = _git_head(repo)
    (repo / "docs" / "note.md").write_text("hello world\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "docs")
    current_head = _git_head(repo)
    ci_input_digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=run_head, ci_input_digest=ci_input_digest)
    _write_lightweight_receipt(repo, head=current_head)
    _write_environment_evidence_for_head(repo)
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        repo / ".artifacts/ci/ci-summary.json",
        format_json=True,
    )
    assert code == 0
    assert payload.get("match") == "reused-non-ci-change"
    assert payload.get("gitHeadAtRun") == run_head
    assert payload.get("gitHead") == current_head


def test_release_mode_rejects_reused_evidence(
    evidence_mod, synced_environment_template: Path, tmp_path: Path
) -> None:
    repo = _init_repo_with_docs(tmp_path, synced_environment_template)
    run_head = _git_head(repo)
    ci_input_digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=run_head, ci_input_digest=ci_input_digest)
    (repo / "docs" / "note.md").write_text("updated\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "docs")
    _write_lightweight_receipt(repo, head=_git_head(repo))
    _write_environment_evidence_for_head(repo)
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        repo / ".artifacts/ci/ci-summary.json",
        format_json=True,
        release=True,
    )
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.head-mismatch"


def test_ci_input_mismatch_rejects_reuse(
    evidence_mod, synced_environment_template: Path, tmp_path: Path
) -> None:
    repo = _init_repo_with_product(tmp_path, synced_environment_template)
    run_head = _git_head(repo)
    ci_input_digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=run_head, ci_input_digest=ci_input_digest)
    (repo / "spell_sync" / "sample.py").write_text("x = 99\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "product")
    _write_lightweight_receipt(repo, head=_git_head(repo))
    _write_environment_evidence_for_head(repo)
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        repo / ".artifacts/ci/ci-summary.json",
        format_json=True,
    )
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.ci-input-mismatch"


def test_stale_lightweight_receipt_rejects_reuse(
    evidence_mod, synced_environment_template: Path, tmp_path: Path
) -> None:
    repo = _init_repo_with_docs(tmp_path, synced_environment_template)
    run_head = _git_head(repo)
    ci_input_digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=run_head, ci_input_digest=ci_input_digest)
    (repo / "docs" / "note.md").write_text("updated\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "docs")
    current_head = _git_head(repo)
    _write_lightweight_receipt(repo, head=current_head, documentation_digest="stale")
    _write_environment_evidence_for_head(repo)
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        repo / ".artifacts/ci/ci-summary.json",
        format_json=True,
    )
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.lightweight-evidence-stale"


def test_run_head_unavailable_fails_safely(
    evidence_mod, synced_environment_template: Path, tmp_path: Path
) -> None:
    repo = _init_repo_with_docs(tmp_path, synced_environment_template)
    ci_input_digest = _compute_ci_input_digest(repo)
    missing_head = "0" * 40
    _write_summary(repo, head=missing_head, ci_input_digest=ci_input_digest)
    (repo / "docs" / "note.md").write_text("updated\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "docs")
    _write_lightweight_receipt(repo, head=_git_head(repo))
    _write_environment_evidence_for_head(repo)
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        repo / ".artifacts/ci/ci-summary.json",
        format_json=True,
    )
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.run-head-unavailable"


def test_exact_head_evidence_still_valid(
    evidence_mod, synced_environment_template: Path, tmp_path: Path
) -> None:
    repo = _init_repo_with_product(tmp_path, synced_environment_template)
    head = _git_head(repo)
    ci_input_digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=head, ci_input_digest=ci_input_digest)
    _write_environment_evidence_for_head(repo)
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        repo / ".artifacts/ci/ci-summary.json",
        format_json=True,
    )
    assert code == 0
    assert payload.get("match") == "exact-head"


def _init_git(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)


def _git_add_all(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)


def _git_commit(repo: Path, message: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True
    )


def _git_head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _compute_ci_input_digest(repo: Path) -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.ci_impact.registry import load_registry
    from scripts.ci_input_state import compute_ci_input_state

    return compute_ci_input_state(repo, load_registry(repo / "ci" / "ci-impact.toml")).digest


def _write_summary(repo: Path, *, head: str, ci_input_digest: str) -> None:
    from scripts.test_selection.tree_state import content_tree_digest

    digest = content_tree_digest(repo)
    fingerprint = _environment_fingerprint(repo)
    artifacts = repo / ".artifacts" / "ci"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 4,
        "runId": "test-run",
        "result": "success",
        "exitCode": 0,
        "mode": "full",
        "finalEvidence": True,
        "gitHeadAtRun": head,
        "gitHead": head,
        "gitBranch": "main",
        "gitDetached": False,
        "repositoryTreeDigest": digest,
        "treeDigest": digest,
        "treeDigestBefore": digest,
        "treeDigestAfter": digest,
        "treeStable": True,
        "ciInputDigest": ci_input_digest,
        "ciImpactSchemaVersion": 1,
        "evidenceScope": "full-ci-inputs",
        "reusableAcrossNonCiCommits": True,
        "historyAtCompletion": {"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1},
        "fullCiAttempts": 1,
        "fullCiFailures": 0,
        "fullCiSuccesses": 1,
        "environmentFingerprint": fingerprint.signature(),
        "environmentContractDigest": fingerprint.environment_contract_digest,
        "pyprojectDigest": fingerprint.pyproject_digest,
        "uvLockDigest": fingerprint.uv_lock_digest,
        "installedEnvironmentDigest": fingerprint.installed_environment_digest,
        "pythonVersion": fingerprint.python_version,
        "pythonImplementation": fingerprint.python_implementation,
        "pythonCacheTag": fingerprint.python_cache_tag,
        "uvVersion": fingerprint.uv_version,
        "checks": [{"id": "tests.pytest", "status": "passed", "exitCode": 0}],
    }
    summary_path = artifacts / "ci-summary.json"
    summary_path.write_text(json.dumps(payload), encoding="utf-8")
    (artifacts / "ci-summary-test-run.json").write_text(json.dumps(payload), encoding="utf-8")
    (artifacts / "ci-run-test-run.log").write_text("ok\n", encoding="utf-8")


def _write_lightweight_receipt(
    repo: Path, *, head: str, documentation_digest: str | None = None
) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.ci_impact.registry import load_registry
    from scripts.documentation_state import compute_documentation_state

    doc_state = compute_documentation_state(repo, load_registry(repo / "ci" / "ci-impact.toml"))
    receipt = {
        "schemaVersion": 1,
        "gitHead": head,
        "documentationDigest": documentation_digest or doc_state.digest,
        "changeClasses": ["documentation"],
        "commands": [],
        "result": "success",
        "completedAt": "2026-07-22T00:00:00Z",
    }
    path = repo / ".artifacts/lightweight-validation/current.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt), encoding="utf-8")
