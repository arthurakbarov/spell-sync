"""CLI import path stays free of Textual until UI launch; cold-start budget smoke."""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Catastrophic regression budgets (lazy Textual must keep CLI cold start cheap).
# Generous for CI hosts; still fails if Textual is pulled into import again.
CLI_IMPORT_BUDGET_MS = 750.0
STATUS_JSON_BUDGET_MS = 2500.0


def test_cli_import_does_not_load_textual() -> None:
    script = """
import sys
import spell_sync.cli  # noqa: F401
loaded = [name for name in sys.modules if name == "textual" or name.startswith("textual.")]
assert not loaded, loaded
assert "spell_sync.tui.launch" not in sys.modules
assert "spell_sync.tui.app" not in sys.modules
print("ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "ok" in proc.stdout


def test_cli_import_cold_start_within_budget() -> None:
    script = """
import time
start = time.perf_counter()
import spell_sync.cli  # noqa: F401
elapsed_ms = (time.perf_counter() - start) * 1000.0
print(f"{elapsed_ms:.3f}")
"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    elapsed_ms = float(proc.stdout.strip().splitlines()[-1])
    assert elapsed_ms < CLI_IMPORT_BUDGET_MS, (
        f"spell_sync.cli import took {elapsed_ms:.1f}ms (budget {CLI_IMPORT_BUDGET_MS}ms)"
    )


def test_status_json_cold_start_within_budget(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    (tmp_path / "spell-sync.toml").write_text(
        "[dictionaries]\nchrome = false\neditors = false\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    start = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "spell_sync",
            "status",
            "--json",
            "--wordlist",
            str(wordlist),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert '"command"' in proc.stdout or '"exit"' in proc.stdout
    assert elapsed_ms < STATUS_JSON_BUDGET_MS, (
        f"status --json took {elapsed_ms:.1f}ms (budget {STATUS_JSON_BUDGET_MS}ms)"
    )
