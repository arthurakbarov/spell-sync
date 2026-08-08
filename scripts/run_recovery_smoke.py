#!/usr/bin/env python3
"""Non-mutating recovery smoke: inspect recover dry-run / absent journal."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Project root with wordlist (default: cwd)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args(argv)
    project = (args.project or Path.cwd()).expanduser().resolve()
    cmd = [
        sys.executable,
        "-m",
        "spell_sync",
        "recover",
        "--dry-run",
        "--json",
        "--project",
        str(project),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False, capture_output=True, text=True)
    payload: dict[str, object] = {
        "command": "recovery-smoke",
        "exit": proc.returncode,
        "project": str(project),
    }
    if proc.returncode != 0:
        payload["stderr"] = (proc.stderr or "")[-2000:]
        payload["stdout"] = (proc.stdout or "")[-2000:]
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("RECOVERY_SMOKE_RESULT=failed", file=sys.stderr)
            print(proc.stderr or proc.stdout or "", file=sys.stderr)
        return 1
    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {"raw": proc.stdout}
    action = data.get("action") if isinstance(data, dict) else None
    status = "absent-or-ok" if action in {None, "none"} else str(action)
    payload["recoverAction"] = action
    payload["status"] = status
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("RECOVERY_SMOKE_RESULT=success")
        print(f"RECOVERY_SMOKE_ACTION={action or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
