"""Tests for scripts/check_session.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_session  # noqa: E402


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "add", "-A"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "commit", "-qm", "init"],
        cwd=path,
        check=True,
    )


def test_start_record_lookup_finish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "sessions"
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_DIR", str(base))
    monkeypatch.delenv("SPELL_SYNC_CHECK_SESSION_ID", raising=False)
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)

    sid = check_session.start_session(base=base)
    assert (base / ".current-session").read_text(encoding="utf-8") == sid

    fp = check_session.tree_fingerprint(repo)
    check_session.record_check(
        "docs.contract",
        exit_code=0,
        duration=1.5,
        session_id=sid,
        root=repo,
        base=base,
        fingerprint=fp,
    )
    reused = check_session.lookup_reusable(
        "docs.contract",
        session_id=sid,
        root=repo,
        base=base,
        fingerprint=fp,
    )
    assert reused is not None
    assert reused["exitCode"] == 0
    assert reused["reused"] is False

    # Dirty tree changes fingerprint → no reuse
    (repo / "README").write_text("changed\n", encoding="utf-8")
    dirty_fp = check_session.tree_fingerprint(repo)
    assert dirty_fp != fp
    assert (
        check_session.lookup_reusable(
            "docs.contract",
            session_id=sid,
            root=repo,
            base=base,
            fingerprint=dirty_fp,
        )
        is None
    )

    finished = check_session.finish_session(sid, base=base)
    assert finished == sid
    assert not (base / ".current-session").exists()
    meta = json.loads((base / sid / "session.json").read_text(encoding="utf-8"))
    assert meta["status"] == "finished"


def test_cli_start_status_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "sessions"
    monkeypatch.setenv("SPELL_SYNC_CHECK_SESSION_DIR", str(base))
    monkeypatch.delenv("SPELL_SYNC_CHECK_SESSION_ID", raising=False)
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)

    assert check_session.main(["start", "--json"]) == 0
    # resolve via current file
    assert check_session.main(["status", "--json"]) == 0
    assert check_session.main(["finish", "--json"]) == 0


def test_failed_record_is_not_reusable(tmp_path: Path) -> None:
    base = tmp_path / "sessions"
    repo = tmp_path / "repo"
    _init_repo(repo)
    sid = check_session.start_session(session_id="arc-test", base=base)
    fp = check_session.tree_fingerprint(repo)
    check_session.record_check(
        "unit",
        exit_code=1,
        session_id=sid,
        root=repo,
        base=base,
        fingerprint=fp,
    )
    assert (
        check_session.lookup_reusable(
            "unit",
            session_id=sid,
            root=repo,
            base=base,
            fingerprint=fp,
        )
        is None
    )
