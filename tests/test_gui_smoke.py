#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless command scenarios retained from the former manual GUI harness."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run(wordlist: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "spell_sync", command, "-C", str(wordlist), "--json"],
        cwd=wordlist.parent,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("command", ["doctor", "status", "lint"])
def test_headless_command_scenarios(tmp_path: Path, command: str) -> None:
    wordlist = tmp_path / "wordlist.txt"
    subprocess.run(
        [sys.executable, "-m", "spell_sync", "init", "-C", str(wordlist)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    result = _run(wordlist, command)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == command
    assert payload["exit"] == 0
