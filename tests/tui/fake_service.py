"""Shared TUI test helpers."""

from __future__ import annotations

from dataclasses import dataclass

from spell_sync.application.reports import DashboardState, PushPreviewSnapshot, StatusSnapshot
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.sync_models import DictionaryDiff, PushResult


@dataclass
class FakeTuiService:
    dashboard_state: DashboardState
    status_snapshot: StatusSnapshot
    preview_snapshot: PushPreviewSnapshot

    def load_dashboard(self, opts: CliOptions) -> DashboardState:
        return self.dashboard_state

    def load_status(self, opts: CliOptions) -> StatusSnapshot:
        return self.status_snapshot

    def load_push_preview(self, opts: CliOptions) -> PushPreviewSnapshot:
        return self.preview_snapshot


def sample_status() -> StatusSnapshot:
    return StatusSnapshot(
        wordlist_count=3,
        diffs=(
            DictionaryDiff(
                name="chrome",
                target_count=3,
                local_count=5,
                to_add=0,
                to_remove=2,
            ),
        ),
        skipped_unreadable=(),
        skipped_corrupt=(),
    )


def sample_dashboard() -> DashboardState:
    return DashboardState(
        wordlist_path="/tmp/wordlist.txt",
        config_status="valid",
        config_valid=True,
        targets_detected=2,
        snapshot=sample_status(),
    )


def sample_preview() -> PushPreviewSnapshot:
    diff = DictionaryDiff(
        name="chrome",
        target_count=3,
        local_count=5,
        to_add=0,
        to_remove=2,
    )
    return PushPreviewSnapshot(
        diffs=(diff,),
        plan_result=PushResult(word_count=3, written=("chrome",)),
        wordlist_error=None,
    )


def fake_service(
    *,
    wordlist_error: ExitCode | None = None,
    config_valid: bool = True,
    config_status: str = "valid",
    empty_wordlist: bool = False,
    preview_unchanged: bool = False,
    plan_blocked: bool = False,
) -> FakeTuiService:
    status = sample_status()
    if wordlist_error is not None:
        status = StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
            wordlist_error=wordlist_error,
        )
    elif empty_wordlist:
        status = StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
            empty_wordlist=True,
        )
    dashboard = DashboardState(
        wordlist_path="/tmp/wordlist.txt",
        config_status=config_status,
        config_valid=config_valid,
        targets_detected=1,
        snapshot=status,
    )
    preview = PushPreviewSnapshot(
        diffs=(),
        plan_result=wordlist_error,
        wordlist_error=wordlist_error,
    )
    if wordlist_error is None:
        if preview_unchanged:
            diff = DictionaryDiff(
                name="chrome",
                target_count=3,
                local_count=3,
                to_add=0,
                to_remove=0,
            )
            preview = PushPreviewSnapshot(
                diffs=(diff,),
                plan_result=PushResult(word_count=3, written=("chrome",)),
                wordlist_error=None,
            )
        elif plan_blocked:
            diff = DictionaryDiff(
                name="chrome",
                target_count=3,
                local_count=5,
                to_add=0,
                to_remove=2,
            )
            preview = PushPreviewSnapshot(
                diffs=(diff,),
                plan_result=ExitCode.PUSH_ABORT,
                wordlist_error=None,
            )
        else:
            preview = sample_preview()
    return FakeTuiService(dashboard, status, preview)
