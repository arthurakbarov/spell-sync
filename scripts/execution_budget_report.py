#!/usr/bin/env python3
"""Report execution budget history and predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.registry import REGISTRY_REL_PATH, load_registry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report execution budget history.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--execution-id", default=None)
    args = parser.parse_args(argv)
    registry = load_registry(ROOT / REGISTRY_REL_PATH)
    history = HistoryStore.open()
    payload = {
        "degraded": history.degraded,
        "database": str(history.path),
        "globalHardCapSeconds": registry.global_hard_cap_seconds,
        "profiles": sorted(registry.profiles),
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("EXECUTION_BUDGET_REPORT=success")
        print(f"EXECUTION_HISTORY_DEGRADED={'true' if history.degraded else 'false'}")
        print(f"EXECUTION_HISTORY_PATH={history.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
