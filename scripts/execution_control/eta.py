"""Pre-run ETA announce for long budgeted and observed commands."""

from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .history import HistoryStore
from .models import ExecutionPlan

DEFAULT_ANNOUNCE_THRESHOLD = 5.0
PROMPT_ALLOWANCE_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class EtaAnnouncement:
    execution_id: str
    work_seconds: float
    prompt_count: int = 0
    source: str = "plan"
    threshold: float = DEFAULT_ANNOUNCE_THRESHOLD

    @property
    def interactive_seconds(self) -> float:
        return max(0, int(self.prompt_count)) * PROMPT_ALLOWANCE_SECONDS

    @property
    def display_seconds(self) -> float:
        return float(self.work_seconds) + self.interactive_seconds

    @property
    def should_announce(self) -> bool:
        return self.display_seconds > self.threshold


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def eta_config_path(*, root: Path | None = None) -> Path:
    env = os.environ.get("SPELL_SYNC_ETA_CONFIG_PATH", "").strip()
    if env:
        return Path(env)
    return (root or _repo_root()) / "config" / "command-eta.json"


def load_eta_config(*, root: Path | None = None) -> dict[str, Any]:
    path = eta_config_path(root=root)
    if not path.is_file():
        return {
            "schemaVersion": 1,
            "announceThresholdSeconds": DEFAULT_ANNOUNCE_THRESHOLD,
            "promptAllowanceSeconds": PROMPT_ALLOWANCE_SECONDS,
            "commands": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def format_eta_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes <= 0:
        return f"{secs}s"
    return f"{minutes}m{secs:02d}s"


def format_announcement(ann: EtaAnnouncement) -> str:
    base = f"eta: expected ~{format_eta_seconds(ann.display_seconds)} ({ann.execution_id})"
    if ann.prompt_count > 0:
        base += (
            f" [work ~{format_eta_seconds(ann.work_seconds)}"
            f" + {format_eta_seconds(ann.interactive_seconds)}"
            f" interactive ×{ann.prompt_count}]"
        )
    return base


def estimate_work_seconds(
    execution_id: str,
    *,
    root: Path | None = None,
    history: HistoryStore | None = None,
    config: dict[str, Any] | None = None,
    hint: float | None = None,
) -> tuple[float, str, int]:
    """Return (work_seconds, source, sample_count). History median wins when present."""
    cfg = config or load_eta_config(root=root)
    commands = cfg.get("commands") if isinstance(cfg.get("commands"), dict) else {}
    meta = commands.get(execution_id) if isinstance(commands, dict) else None
    override: float | None = None
    if isinstance(meta, dict) and meta.get("estimatedSeconds") is not None:
        override = float(meta["estimatedSeconds"])

    source = "hint" if hint is not None else "unknown"
    work = float(hint) if hint is not None else 0.0
    if override is not None and override > 0:
        work = override
        source = "config"

    store = history
    close = False
    samples = 0
    if store is None:
        try:
            store = HistoryStore.open()
            close = True
        except OSError:
            store = None
    try:
        if store is not None:
            durations = store.fetch_profile_durations(execution_id=execution_id, limit=30)
            samples = len(durations)
            if durations:
                work = float(statistics.median(durations))
                source = "history"
    finally:
        if close and store is not None:
            store.close()
    return work, source, samples


def compute_announcement(
    plan: ExecutionPlan,
    *,
    root: Path | None = None,
    history: HistoryStore | None = None,
    config: dict[str, Any] | None = None,
    prompt_count: int | None = None,
) -> EtaAnnouncement | None:
    cfg = config or load_eta_config(root=root)
    threshold = float(cfg.get("announceThresholdSeconds", DEFAULT_ANNOUNCE_THRESHOLD))
    work, source, _samples = estimate_work_seconds(
        plan.execution_id,
        root=root,
        history=history,
        config=cfg,
        hint=float(plan.expected_seconds),
    )
    prompts = (
        int(prompt_count)
        if prompt_count is not None
        else int(getattr(plan, "expected_prompt_count", 0) or 0)
    )
    ann = EtaAnnouncement(
        execution_id=plan.execution_id,
        work_seconds=work,
        prompt_count=prompts,
        source=source,
        threshold=threshold,
    )
    if not ann.should_announce:
        return None
    return ann


def announce_expected_eta(
    execution_id: str,
    *,
    work_seconds: float | None = None,
    prompt_count: int = 0,
    root: Path | None = None,
    history: HistoryStore | None = None,
    config: dict[str, Any] | None = None,
    hint: float | None = None,
    stream: TextIO | None = None,
) -> EtaAnnouncement | None:
    if os.environ.get("SPELL_SYNC_ETA_ANNOUNCE", "1") == "0":
        return None
    if os.environ.get("SPELL_SYNC_JSON_OUTPUT", "0") == "1":
        return None
    cfg = config or load_eta_config(root=root)
    threshold = float(cfg.get("announceThresholdSeconds", DEFAULT_ANNOUNCE_THRESHOLD))
    if work_seconds is None:
        work, source, _samples = estimate_work_seconds(
            execution_id,
            root=root,
            history=history,
            config=cfg,
            hint=hint,
        )
    else:
        work = float(work_seconds)
        source = "hint" if hint is not None else "plan"
        # Prefer history/config when available for the same id.
        hist_work, hist_source, samples = estimate_work_seconds(
            execution_id,
            root=root,
            history=history,
            config=cfg,
            hint=work,
        )
        if samples > 0 or hist_source == "config":
            work = hist_work
            source = hist_source
    ann = EtaAnnouncement(
        execution_id=execution_id,
        work_seconds=work,
        prompt_count=int(prompt_count),
        source=source,
        threshold=threshold,
    )
    if not ann.should_announce:
        return None
    out = stream if stream is not None else sys.stderr
    out.write(format_announcement(ann) + "\n")
    out.flush()
    return ann


def announce_plan_eta(
    plan: ExecutionPlan,
    *,
    root: Path | None = None,
    history: HistoryStore | None = None,
    stream: TextIO | None = None,
) -> EtaAnnouncement | None:
    if os.environ.get("SPELL_SYNC_ETA_ANNOUNCE", "1") == "0":
        return None
    if os.environ.get("SPELL_SYNC_JSON_OUTPUT", "0") == "1":
        return None
    ann = compute_announcement(plan, root=root, history=history)
    if ann is None:
        return None
    out = stream if stream is not None else sys.stderr
    out.write(format_announcement(ann) + "\n")
    out.flush()
    return ann
