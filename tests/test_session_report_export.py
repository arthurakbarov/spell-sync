"""Review session report export tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spell_sync.application.reports import (
    OperationOutcome,
    OperationReport,
    PullPreview,
    PullSourcePreview,
    PushPreview,
    TargetPreview,
    TargetUpdateReport,
)
from spell_sync.application.requests import ProjectRef
from spell_sync.application.review_session import ReviewSession
from spell_sync.application.session_report_export import (
    build_session_report_export,
    default_session_report_path,
    export_session_report,
)
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.tui.controller import TuiController

SENSITIVE = (
    "secret-token-like-value",
    "user@example.com",
    "personal-project-name",
    "/Users/private-name",
)


def _pull_preview() -> PullPreview:
    return PullPreview(
        wordlist_path="/tmp/wordlist.txt",
        additions=2,
        before_count=1,
        after_count=3,
        sources_used=("editors",),
        sources_skipped=(),
        source_rows=(
            PullSourcePreview(
                name="editors",
                status="ready",
                words_contributed=2,
            ),
        ),
        warnings=(),
        created_at="2026-07-20T00:00:00+00:00",
        plan_identifier="plan-1234567890abcdef",
        merged_words=("secret-token-like-value", "alpha", "beta"),
        addition_words=frozenset({"secret-token-like-value", "alpha"}),
    )


def _push_preview() -> PushPreview:
    return PushPreview(
        prepared=None,
        targets=(
            TargetPreview(
                name="editors",
                additions=1,
                removals=0,
                status="Ready",
            ),
        ),
        additions=1,
        removals=0,
        warnings=(),
        created_at="2026-07-20T00:00:00+00:00",
        plan_identifier="push-plan-1234567890",
        targets_to_update=1,
        unchanged=0,
        skipped=(),
        corrupt=(),
        blocked=(),
    )


def _completed_pull_report() -> OperationReport:
    return OperationReport(
        operation="pull",
        outcome=OperationOutcome.COMPLETED,
        title="Pull completed",
        summary="Pull completed.",
    )


def _completed_push_report() -> OperationReport:
    return OperationReport(
        operation="push",
        outcome=OperationOutcome.COMPLETED,
        title="Push completed",
        summary="Push completed.",
        target_updates=(
            TargetUpdateReport(
                name="editors",
                additions=1,
                removals=0,
                status="Updated",
            ),
        ),
    )


def test_session_export_json_no_words(tmp_path: Path) -> None:
    session = ReviewSession(
        pull_preview=_pull_preview(),
        pull_report=_completed_pull_report(),
        push_preview=_push_preview(),
        push_report=_completed_push_report(),
    )
    export = build_session_report_export(session, pending_recovery=False)
    payload = json.dumps(export.__dict__, sort_keys=True)
    for token in SENSITIVE:
        assert token not in payload


def test_session_export_text_and_collision(tmp_path: Path) -> None:
    session = ReviewSession(pull_skipped=True, push_skipped=True)
    export = build_session_report_export(session)
    output = tmp_path / "review-report.json"
    export_session_report(export, output_path=output, fmt="json")
    assert output.is_file()
    with pytest.raises(FileExistsError):
        export_session_report(export, output_path=output, fmt="text")

    root = tmp_path / "state"
    first_json = default_session_report_path(state_root=root, fmt="json")
    first_json.write_text("{}", encoding="utf-8")
    second_json = default_session_report_path(state_root=root, fmt="json")
    assert second_json.suffix == ".json"
    assert second_json != first_json

    first_txt = default_session_report_path(state_root=root, fmt="text")
    first_txt.write_text("existing", encoding="utf-8")
    second_txt = default_session_report_path(state_root=root, fmt="text")
    assert second_txt.suffix == ".txt"
    assert second_txt != first_txt


def test_session_export_skipped_pull_push() -> None:
    session = ReviewSession(pull_skipped=True, push_skipped=True)
    export = build_session_report_export(session)
    assert export.pull_status == "Skipped"
    assert export.push_status == "Skipped"
    assert export.pull_planned_additions is None


def test_controller_export_does_not_create_history_record(tmp_path: Path) -> None:
    from spell_sync.application.service import SpellSyncService

    state = resolve_app_state_paths(state_root=tmp_path / "state")
    service = SpellSyncService(state_paths=state, enable_file_logging=False)
    before_count = len(service.load_operation_history(limit=10).records)
    controller = TuiController(service, ProjectRef())
    controller.begin_review_session()
    session = controller.review_session()
    assert session is not None
    session.pull_skipped = True
    session.push_skipped = True
    path = controller.export_review_session_report(fmt="json")
    assert path.is_file()
    after_count = len(service.load_operation_history(limit=10).records)
    assert after_count == before_count


def test_session_export_recovery_required() -> None:
    session = ReviewSession(
        push_report=OperationReport(
            operation="push",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Recovery required",
            summary="Recovery required.",
            recovery_required=True,
        )
    )
    export = build_session_report_export(session, pending_recovery=True)
    assert export.recovery_required is True
