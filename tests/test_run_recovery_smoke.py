"""Recovery smoke wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from scripts import run_recovery_smoke


def test_recovery_smoke_success_absent(tmp_path: Path, capsys) -> None:
    project = tmp_path / "words"
    project.mkdir()
    fake = mock.Mock(
        returncode=0,
        stdout='{"action":"none","exit":0}\n',
        stderr="",
    )
    with mock.patch("scripts.run_recovery_smoke.subprocess.run", return_value=fake):
        code = run_recovery_smoke.main(["--project", str(project)])
    assert code == 0
    out = capsys.readouterr().out
    assert "RECOVERY_SMOKE_RESULT=success" in out


def test_recovery_smoke_failure(tmp_path: Path) -> None:
    project = tmp_path / "words"
    project.mkdir()
    fake = mock.Mock(returncode=1, stdout="", stderr="boom")
    with mock.patch("scripts.run_recovery_smoke.subprocess.run", return_value=fake):
        assert run_recovery_smoke.main(["--project", str(project)]) == 1
