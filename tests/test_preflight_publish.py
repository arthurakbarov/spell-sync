"""preflight_publish.py readiness plan without executing full CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preflight_publish.py"


def test_preflight_plan_mode_prints_next_steps() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    # Dirty trees are allowed to block (exit 2); clean trees return 0 with a plan.
    # Privacy failures return non-zero with PREFLIGHT_REASON=privacy.
    assert proc.returncode in {0, 2}, proc.stderr + proc.stdout
    assert "PREFLIGHT_STAGE=clean-tree" in proc.stdout
    if proc.returncode == 2:
        assert "PREFLIGHT_REASON=dirty-working-tree" in proc.stdout
        return
    assert "PREFLIGHT_RESULT=ready-plan" in proc.stdout
    assert "PREFLIGHT_NEXT=scripts/ci.sh" in proc.stdout
    assert "PREFLIGHT_STAGE=privacy" in proc.stdout
    assert "PREFLIGHT_PRIVACY=success" in proc.stdout
    assert "privacy-export" in proc.stdout
