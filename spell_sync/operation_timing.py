"""Product operation duration estimates (CLI + TUI).

Stores only operation keys and numeric seconds under the app state directory —
never paths or user words.
"""

import json
import math
import os
import statistics
import threading
from pathlib import Path

# Initial guidance (seconds). Announce when expected >= THRESHOLD.
INITIAL_EXPECTED_SECONDS: dict[str, int] = {
    "pull": 20,
    "push": 45,
    "recover": 25,
    "cleanup": 15,
    "discard": 10,
    "setup": 8,
    "init": 8,
    "add": 3,
    "targets": 6,
    "doctor": 10,
    "git-save": 5,
    "status": 6,
    "plan": 12,
    "lint": 8,
    "config-check": 4,
    "support-report": 15,
    "version": 1,
    "pull_preview": 12,
    "push_preview": 20,
    "recovery_preview": 10,
    "support_export": 15,
    "history_load": 5,
    "dashboard": 3,
    "extra_words_scan": 8,
}

THRESHOLD_SECONDS = 5
_MAX_SAMPLES = 30
_LEARNING_WEIGHT_CAP = 0.65
_lock = threading.Lock()
_store_override: Path | None = None


def _eta_enabled() -> bool:
    return os.environ.get("SPELL_SYNC_OPERATION_ETA", "1") != "0"


def _hang_enabled() -> bool:
    return os.environ.get("SPELL_SYNC_OPERATION_HANG", "1") != "0"


def set_timing_store_path(path: Path | None) -> None:
    """Tests: redirect the learned timing file."""
    global _store_override
    _store_override = path


def timing_store_path() -> Path:
    if _store_override is not None:
        return _store_override
    from .diagnostics.paths import resolve_app_state_paths

    return resolve_app_state_paths().state_directory / "operation-timing.json"


def _load_samples() -> dict[str, list[float]]:
    path = timing_store_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError, json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[float]] = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not isinstance(values, list):
            continue
        samples = [
            float(item)
            for item in values
            if (
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
                and item > 0
            )
        ]
        if samples:
            out[key] = samples[-_MAX_SAMPLES:]
    return out


def _save_samples(samples: dict[str, list[float]]) -> None:
    path = timing_store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(samples, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return


def expected_seconds(operation_key: str) -> int | None:
    """Blended expected wall seconds, or None when unknown."""
    initial = INITIAL_EXPECTED_SECONDS.get(operation_key)
    with _lock:
        samples = _load_samples().get(operation_key, [])
    if initial is None and not samples:
        return None
    if not samples:
        return initial
    median = statistics.median(samples)
    if initial is None:
        return max(1, round(median))
    weight = min(_LEARNING_WEIGHT_CAP, 0.15 * len(samples))
    blended = (1.0 - weight) * float(initial) + weight * float(median)
    return max(1, round(blended))


def record_sample(operation_key: str, seconds: float) -> None:
    """Record a successful human-mode duration sample."""
    if not math.isfinite(seconds) or seconds <= 0:
        return
    if operation_key not in INITIAL_EXPECTED_SECONDS and not operation_key:
        return
    with _lock:
        data = _load_samples()
        bucket = data.setdefault(operation_key, [])
        bucket.append(float(seconds))
        data[operation_key] = bucket[-_MAX_SAMPLES:]
        _save_samples(data)


def format_duration_hint(seconds: int) -> str:
    if seconds < 60:
        return f"Usually takes about {seconds} seconds."
    minutes = max(1, round(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Usually takes about {minutes} {unit}."


def eta_line(operation_key: str) -> str | None:
    """Human ETA line when enabled and expected duration >= threshold."""
    if not _eta_enabled():
        return None
    seconds = expected_seconds(operation_key)
    if seconds is None or seconds < THRESHOLD_SECONDS:
        return None
    return format_duration_hint(seconds)


def hang_threshold_seconds(operation_key: str) -> float:
    """Silence before a Still working heartbeat."""
    if not _hang_enabled():
        return float("inf")
    expected = expected_seconds(operation_key) or 10
    return float(max(15, min(60, expected)))
