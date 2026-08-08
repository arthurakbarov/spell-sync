"""Coverage tests for Spell Sync 1.0.0 transparency features."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.application.requests import ProjectRef, SupportReportRequest
from spell_sync.application.review_session import ReviewSession
from spell_sync.application.service import SpellSyncService
from spell_sync.application.session_report_export import (
    SessionReportExport,
    _recovery_required,
    default_session_report_path,
    export_session_report,
)
from spell_sync.application.support_report import (
    InstallationInfo,
    PrivacyManifest,
    ProjectSupportState,
    RecoverySupportState,
    SupportNotice,
    SupportReport,
    default_support_report_path,
    export_support_report,
    format_support_report_text,
    sanitize_support_payload,
)
from spell_sync.application.target_details import build_target_details, format_target_details_text
from spell_sync.cli_options import CliOptions
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.project_setup.discovery import SetupTarget
from spell_sync.support.path_redaction import redact_path, redact_text
from spell_sync.support_report_cmd import cmd_support_report
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.doctor_screen import DoctorScreen
from spell_sync.tui.screens.review_update_screen import ReviewSessionReportScreen
from spell_sync.tui.screens.target_settings_screen import TargetSettingsScreen
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import wait_for_text


def _target(identifier: str, **kwargs: object) -> SetupTarget:
    defaults = dict(
        display_name=identifier.title(),
        path=Path("/tmp/dict.txt"),
        format_name="text",
        detected=True,
        available=True,
        readable=True,
        supported=True,
        enabled_by_default=True,
        selectable=True,
        word_count=1,
        status="ok",
        detail=None,
        enabled=True,
    )
    defaults.update(kwargs)
    return SetupTarget(identifier=identifier, **defaults)  # type: ignore[arg-type]


def test_target_details_filtering_and_states() -> None:
    latin = build_target_details(_target("win_spelling"))
    assert "canonical" in latin.filtering_label.lower()
    corrupt = build_target_details(
        _target("chrome", status="corrupt"),
        suggested_action="Repair file.",
    )
    assert corrupt.runtime_state == "Corrupt"
    assert "Repair file." in format_target_details_text(corrupt)
    unreadable = build_target_details(_target("firefox", status="unreadable"))
    assert unreadable.runtime_state == "Unreadable"
    disabled = build_target_details(_target("edge", enabled=False, detected=False))
    assert disabled.runtime_state in {"Disabled", "Unavailable", "Needs attention"}


def test_target_details_without_validation_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: None,
    )
    details = build_target_details(_target("chrome"))
    assert details.manual_validation == "not-run"


def test_support_report_notices_and_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = home / "project"
    project.mkdir()
    wordlist = project / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    wordlist.write_text("invalid toml should not appear", encoding="utf-8")
    wordlist.write_text("alpha\n", encoding="utf-8")
    (project / "spell-sync.toml").write_text("not valid toml [[[\n", encoding="utf-8")
    service = SpellSyncService(
        state_paths=resolve_app_state_paths(state_root=tmp_path / "state"),
        enable_file_logging=False,
    )
    report = service.load_support_report(
        SupportReportRequest(project=ProjectRef(wordlist=wordlist)),
    )
    assert report.project.wordlist_count == 1
    text = format_support_report_text(report)
    assert "Notices" in text or "Invalid configuration" in text


def test_support_report_corrupt_target_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = home / "project"
    project.mkdir()
    wordlist = project / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    example = Path(__file__).resolve().parents[1] / "spell_sync/bundled/spell-sync.toml.example"
    (project / "spell-sync.toml").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    service = SpellSyncService(
        state_paths=resolve_app_state_paths(state_root=tmp_path / "state"),
        enable_file_logging=False,
    )
    corrupt = _target("chrome", status="corrupt", available=False, readable=False)
    with patch(
        "spell_sync.application.support_report.load_target_settings_snapshot",
        return_value=MagicMock(targets=(corrupt,)),
    ):
        report = service.load_support_report(
            SupportReportRequest(project=ProjectRef(wordlist=wordlist)),
        )
    assert any(item.reason_code == "target_corrupt" for item in report.targets)


def test_support_report_export_text_and_errors(tmp_path: Path) -> None:
    report = SupportReport(
        schema_version=1,
        generated_at=datetime.now(timezone.utc),
        spell_sync_version="1.0.0",
        python_version="3.11",
        operating_system="test",
        architecture="arm64",
        installation=InstallationInfo("1.0.0", "test"),
        project=ProjectSupportState(True, 1, False),
        targets=(),
        recovery=RecoverySupportState(False, "absent"),
        recent_operations=(),
        notices=(SupportNotice("code", "Title", "Detail", "Action"),),
        privacy=PrivacyManifest(),
    )
    text_path = tmp_path / "report.txt"
    export_support_report(report, output_path=text_path, fmt="text")
    assert "Notices" in text_path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        export_support_report(report, output_path=tmp_path / "bad.bin", fmt="binary")


def test_default_support_report_path_collision(tmp_path: Path) -> None:
    root = tmp_path / "state"
    first = default_support_report_path(state_root=root, fmt="json")
    first.write_text("{}", encoding="utf-8")
    second = default_support_report_path(state_root=root, fmt="json")
    assert second != first


def test_path_redaction_edge_cases() -> None:
    assert redact_path(None) is None
    assert redact_path("") == ""
    assert redact_text("secret-token-like-value", home=Path("/Users/alice")) == "<redacted>"
    assert redact_path("D:\\data\\dict.txt", home=Path("/tmp/home")) == "<external>/dict.txt"


def test_path_redaction_windows_drive_external_name() -> None:
    from spell_sync.support.path_redaction import _windows_drive_external_name

    assert _windows_drive_external_name("C:/Users/test/dict.txt") == "<external>/dict.txt"
    assert _windows_drive_external_name("/external/only/name") is None


def test_target_details_filtering_labels() -> None:
    from spell_sync.application.target_details import _current_platform, _filtering_label
    from spell_sync.target_capabilities import TargetFilterKind

    assert "Latin" in _filtering_label(TargetFilterKind.LATIN)
    assert "Cyrillic" in _filtering_label(TargetFilterKind.CYRILLIC_AND_NON_LATIN)
    assert _current_platform() in {"macos", "windows", "linux"}


def test_target_details_labels_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    running = build_target_details(_target("chrome"))
    assert "blocked" in running.close_policy_label.lower()
    attention = build_target_details(
        _target("edge", available=False, readable=False, detected=True, status="ok")
    )
    assert attention.runtime_state == "Needs attention"
    payload = {
        "schema_version": 1,
        "targets": [
            {
                "target_id": "chrome",
                "platform": "macos",
                "automated_validation": "pass",
                "manual_validation": "pass",
                "tested_on": "2026-07-01",
            }
        ],
    }
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: payload,
    )
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    validated = build_target_details(_target("chrome"))
    assert validated.manual_validation == "pass"
    assert "Repair" in format_target_details_text(
        build_target_details(_target("chrome"), suggested_action="Repair dictionary file.")
    )


def test_path_redaction_expanduser_failure() -> None:
    original = Path.expanduser

    def flaky_expanduser(self: Path) -> Path:
        if str(self) == "/broken/path":
            raise OSError("bad path")
        return original(self)

    with patch.object(Path, "expanduser", flaky_expanduser):
        assert redact_path("/broken/path", home=Path("/tmp/home")) == "<external>/path"


def test_support_report_unreadable_and_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = home / "project"
    project.mkdir()
    wordlist = project / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    example = Path(__file__).resolve().parents[1] / "spell_sync/bundled/spell-sync.toml.example"
    (project / "spell-sync.toml").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    service = SpellSyncService(
        state_paths=resolve_app_state_paths(state_root=tmp_path / "state"),
        enable_file_logging=False,
    )
    unreadable = _target("firefox", status="unreadable", available=False, readable=False)
    with patch(
        "spell_sync.application.support_report.load_target_settings_snapshot",
        return_value=MagicMock(targets=(unreadable,)),
    ):
        report = service.load_support_report(
            SupportReportRequest(project=ProjectRef(wordlist=wordlist)),
        )
    assert any(item.reason_code == "target_unreadable" for item in report.targets)
    with (
        patch(
            "spell_sync.application._runtime_factory.load_journal_result",
            return_value=MagicMock(
                status=__import__(
                    "spell_sync.push_journal", fromlist=["JournalLoadStatus"]
                ).JournalLoadStatus.VALID_IN_PROGRESS
            ),
        ),
        patch(
            "spell_sync.application.support_report.load_target_settings_snapshot",
            return_value=MagicMock(targets=()),
        ),
    ):
        pending = service.load_support_report(
            SupportReportRequest(project=ProjectRef(wordlist=wordlist)),
        )
    assert pending.recovery.pending_recovery is True


def test_support_report_cmd_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "exists.json"
    output.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "spell_sync.application.support_report.build_support_report",
        lambda *_a, **_k: MagicMock(),
    )
    monkeypatch.setattr(
        "spell_sync.support_report_cmd.support_report_to_dict",
        lambda _report: {"schema_version": 1},
    )
    code = cmd_support_report(
        CliOptions(support_report_output=str(output), support_report_format="json")
    )
    assert code != 0


def test_session_export_unsupported_format(tmp_path: Path) -> None:
    export = SessionReportExport(
        schema_version=1,
        generated_at="2026-01-01T00:00:00+00:00",
        spell_sync_version="1.0.0",
        pull_status="Skipped",
        push_status="Skipped",
        recovery_note="None.",
        pull_planned_additions=None,
        pull_actual_additions=None,
        pull_skipped_sources=None,
        push_planned_updates=None,
        push_actual_updates=None,
        push_skipped_targets=None,
        recovery_required=False,
    )
    with pytest.raises(ValueError):
        export_session_report(export, output_path=tmp_path / "x.bin", fmt="binary")


def test_controller_unreadable_notice() -> None:
    from spell_sync.project_setup.target_settings import TargetSettingsSnapshot

    snapshot = TargetSettingsSnapshot(
        config_path=Path("/tmp/spell-sync.toml"),
        wordlist_path=Path("/tmp/wordlist.txt"),
        targets=(_target("firefox", status="unreadable", readable=False),),
        enabled_target_ids=frozenset({"firefox"}),
    )
    service = fake_service()
    service.load_target_settings = MagicMock(return_value=snapshot)
    controller = TuiController(service, ProjectRef())
    assert controller.target_details("firefox").suggested_action is not None
    with pytest.raises(KeyError):
        controller.target_details("missing-id")


def test_doctor_export_file_exists() -> None:
    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        controller.export_support_report = MagicMock(  # type: ignore[method-assign]
            side_effect=FileExistsError("exists")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(DoctorScreen(controller))
            await pilot.click("#btn-export-support")
            status = await wait_for_text(pilot, "#doctor-export-status", "exists")
            assert "exists" in str(status.render()).lower()

    asyncio.run(_run())


def test_review_save_report_failure() -> None:
    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.pull_skipped = True
        session.push_skipped = True
        controller.export_review_session_report = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("fail")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            await pilot.click("#btn-save-report")
            await wait_for_text(pilot, "#session-report-export-status", "could not be exported")

    asyncio.run(_run())


def test_session_export_text_and_recovery() -> None:
    session = ReviewSession(
        push_report=OperationReport(
            operation="push",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Recovery",
            summary="Recovery required.",
            recovery_required=True,
        )
    )
    assert _recovery_required(session) is True
    export = SessionReportExport(
        schema_version=1,
        generated_at="2026-01-01T00:00:00+00:00",
        spell_sync_version="1.0.0",
        pull_status="Skipped",
        push_status="Recovery required",
        recovery_note="Pending.",
        pull_planned_additions=None,
        pull_actual_additions=None,
        pull_skipped_sources=None,
        push_planned_updates=None,
        push_actual_updates=None,
        push_skipped_targets=None,
        recovery_required=True,
    )
    path = Path("/tmp/session-report-test.txt")
    if path.exists():
        path.unlink()
    export_session_report(export, output_path=path, fmt="text")
    assert "Review session report" in path.read_text(encoding="utf-8")
    path.unlink(missing_ok=True)
    root = Path("/tmp/spell-sync-session-collision")
    root.mkdir(exist_ok=True)
    first = default_session_report_path(state_root=root, fmt="json")
    first.write_text("{}", encoding="utf-8")
    second = default_session_report_path(state_root=root, fmt="json")
    assert second != first


def test_support_report_cmd_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spell_sync.application.support_report.build_support_report",
        lambda *_a, **_k: MagicMock(
            spell_sync_version="1.0.0",
            generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            python_version="3.11",
            operating_system="test",
            architecture="arm64",
            installation=MagicMock(package_version="1.0.0", installation_type="test"),
            project=MagicMock(config_valid=True, wordlist_count=1, pending_recovery=False),
            targets=(),
            recovery=MagicMock(pending_recovery=False, journal_status="absent"),
            recent_operations=(),
            notices=(),
            privacy=MagicMock(
                contains_words=False,
                contains_dictionary_contents=False,
                contains_config_contents=False,
                paths_redacted=True,
                profile_names_redacted=True,
            ),
        ),
    )
    monkeypatch.setattr(
        "spell_sync.support_report_cmd.support_report_to_dict",
        lambda _report: {"schema_version": 1},
    )
    code = cmd_support_report(CliOptions(json_output=True))
    assert code == 0
    output = tmp_path / "out.json"
    code = cmd_support_report(
        CliOptions(json_output=True, support_report_output=str(output)),
    )
    assert code == 0


def test_sanitize_support_payload() -> None:
    assert sanitize_support_payload("alpha beta") == "alpha beta"


def test_controller_target_details_notices() -> None:
    from spell_sync.project_setup.target_settings import TargetSettingsSnapshot

    snapshot = TargetSettingsSnapshot(
        config_path=Path("/tmp/spell-sync.toml"),
        wordlist_path=Path("/tmp/wordlist.txt"),
        targets=(
            _target("chrome", status="corrupt"),
            _target("firefox", status="unreadable"),
        ),
        enabled_target_ids=frozenset({"chrome", "firefox"}),
    )
    service = fake_service()
    service.load_target_settings = MagicMock(return_value=snapshot)
    controller = TuiController(service, ProjectRef())
    assert controller.target_details("chrome").suggested_action is not None
    assert controller.target_details("firefox").suggested_action is not None
    with pytest.raises(KeyError):
        controller.target_details("missing")


def test_target_details_platform_and_validation_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsupported = build_target_details(_target("chrome", supported=False))
    assert unsupported.runtime_state == "Unsupported on this platform"
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert (
        __import__(
            "spell_sync.application.target_details", fromlist=["_current_platform"]
        )._current_platform()
        == "linux"
    )
    monkeypatch.setattr("platform.system", lambda: "Windows")
    assert (
        __import__(
            "spell_sync.application.target_details", fromlist=["_current_platform"]
        )._current_platform()
        == "windows"
    )
    payload = {
        "schema_version": 1,
        "targets": [
            "invalid-row",
            {"target_id": 123, "platform": "macos"},
            {
                "target_id": "chrome",
                "platform": "linux",
                "automated_validation": "pass",
                "manual_validation": "not-run",
            },
        ],
    }
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: payload,
    )
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    details = build_target_details(_target("chrome"))
    assert details.automated_validation == "not-run"


def test_target_details_validation_non_list_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: {"schema_version": 1, "targets": "invalid"},
    )
    details = build_target_details(_target("chrome"))
    assert details.manual_validation == "not-run"


def test_target_details_validation_windows_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spell_sync.application.target_details import _load_validation_lookup

    payload = {
        "schema_version": 1,
        "targets": [
            {
                "target_id": "chrome",
                "platform": "windows",
                "automated_validation": "pass",
                "manual_validation": "not-run",
            }
        ],
    }
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: payload,
    )
    monkeypatch.setattr("platform.system", lambda: "Windows")
    lookup = _load_validation_lookup()
    assert lookup[("chrome", "windows")].automated_validation == "pass"


def test_target_details_validation_linux_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spell_sync.application.target_details import _load_validation_lookup

    payload = {
        "schema_version": 1,
        "targets": [
            {
                "target_id": "chrome",
                "platform": "linux",
                "automated_validation": "pass",
                "manual_validation": "not-run",
            }
        ],
    }
    monkeypatch.setattr(
        "spell_sync.application.target_details.load_packaged_target_validation",
        lambda: payload,
    )
    monkeypatch.setattr("platform.system", lambda: "Linux")
    lookup = _load_validation_lookup()
    assert lookup[("chrome", "linux")].automated_validation == "pass"


def test_target_settings_open_details_without_focus() -> None:
    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            screen = TargetSettingsScreen(controller)
            await pilot.app.mount(screen)
            screen.focused = None
            with patch.object(screen.app, "push_screen") as push_screen:
                screen.action_open_details()
                push_screen.assert_not_called()

    asyncio.run(_run())


def test_doctor_export_generic_failure() -> None:
    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        controller.export_support_report = MagicMock(side_effect=ValueError("fail"))  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(DoctorScreen(controller))
            await pilot.click("#btn-export-support")
            status = await wait_for_text(pilot, "#doctor-export-status", "could not be exported")
            assert "could not be exported" in str(status.render())

    asyncio.run(_run())


def test_review_save_report_file_exists() -> None:
    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.pull_skipped = True
        session.push_skipped = True
        controller.export_review_session_report = MagicMock(  # type: ignore[method-assign]
            side_effect=FileExistsError("exists")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            await pilot.click("#btn-save-report")
            await wait_for_text(pilot, "#session-report-export-status", "exists")

    asyncio.run(_run())


def test_review_save_report_already_saved_message() -> None:
    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            screen = ReviewSessionReportScreen(controller)
            screen._saved_report_path = "/tmp/already-saved.json"
            await app.push_screen(screen)
            await pilot.click("#btn-save-report")
            status = await wait_for_text(pilot, "#session-report-export-status", "Report already saved")
            assert "already saved" in str(status.render()).lower()

    asyncio.run(_run())


def test_review_save_report_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        service = SpellSyncService(
            state_paths=resolve_app_state_paths(state_root=tmp_path / "state"),
            enable_file_logging=False,
        )
        controller = TuiController(service, ProjectRef())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.pull_skipped = True
        session.push_skipped = True
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            await pilot.click("#btn-save-report")
            await wait_for_text(pilot, "#session-report-export-status", "Report saved")

    asyncio.run(_run())


def test_controller_export_methods(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    service = SpellSyncService(
        state_paths=resolve_app_state_paths(state_root=tmp_path / "state"),
        enable_file_logging=False,
    )
    controller = TuiController(service, ProjectRef())
    controller.begin_review_session()
    session = controller.review_session()
    assert session is not None
    session.pull_skipped = True
    session.push_skipped = True
    assert controller.export_review_session_report(fmt="json").is_file()
    assert controller.export_support_report(fmt="json").is_file()


def test_load_packaged_target_validation_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spell_sync.target_validation import load_packaged_target_validation

    monkeypatch.setattr(
        "spell_sync.target_validation.resources.files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    assert load_packaged_target_validation() is None

    class FakeResource:
        def joinpath(self, *_args, **_kwargs) -> FakeResource:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            return "[]"

    monkeypatch.setattr(
        "spell_sync.target_validation.resources.files",
        lambda *_args, **_kwargs: FakeResource(),
    )
    assert load_packaged_target_validation() is None


def test_doctor_export_worker_branches() -> None:
    from textual.worker import Worker, WorkerState

    from spell_sync.tui.export_results import ReportExportResult
    from spell_sync.tui.screens.doctor_screen import DoctorScreen

    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(DoctorScreen(controller))
            screen = app.screen
            assert isinstance(screen, DoctorScreen)
            screen._export_in_progress = True
            screen._export_token = 1
            screen._export_started_token = 1

            running = MagicMock(state=WorkerState.RUNNING)
            screen._export_worker_handle = running
            screen._poll_export_worker()

            success = MagicMock(
                state=WorkerState.SUCCESS,
                result=ReportExportResult(ok=True, path="/tmp/x.json"),
            )
            screen._finish_export_worker(success)

            screen._export_in_progress = True
            screen._finish_export_worker(MagicMock(state=WorkerState.ERROR))

            screen._export_in_progress = True
            screen._finish_export_worker(MagicMock(state=WorkerState.PENDING))

            screen._export_in_progress = True
            screen._export_token = 2
            screen._export_started_token = 1
            screen._finish_export_worker(success)

            screen._export_in_progress = True
            screen._export_token = 1
            screen._finish_export_worker(MagicMock(state=WorkerState.SUCCESS, result="bad"))

            screen._export_in_progress = False
            screen._finish_export_worker(success)

            screen._export_in_progress = True
            screen._export_token = 1
            collision = MagicMock(
                state=WorkerState.SUCCESS,
                result=ReportExportResult(ok=False, message="exists"),
            )
            screen._finish_export_worker(collision)

            done = Worker.StateChanged(success, WorkerState.SUCCESS)
            screen.on_export_support_report_worker_state_changed(done)

            running_event = Worker.StateChanged(
                MagicMock(state=WorkerState.RUNNING), WorkerState.RUNNING
            )
            screen.on_export_support_report_worker_state_changed(running_event)

            screen._export_in_progress = True
            screen._export_support_report()
            screen._export_support_report()
            await pilot.pause()

    asyncio.run(_run())


def test_review_export_worker_branches() -> None:
    from textual.worker import Worker, WorkerState

    from spell_sync.tui.export_results import ReportExportResult
    from spell_sync.tui.screens.review_update_screen import ReviewSessionReportScreen

    async def _run() -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            screen = app.screen
            assert isinstance(screen, ReviewSessionReportScreen)
            screen._export_in_progress = True
            screen._export_token = 1
            screen._export_started_token = 1

            running = MagicMock(state=WorkerState.RUNNING)
            screen._export_worker_handle = running
            screen._poll_export_worker()

            success = MagicMock(
                state=WorkerState.SUCCESS,
                result=ReportExportResult(ok=True, path="/tmp/review-report.json"),
            )
            screen._finish_export_worker(success)
            assert screen._saved_report_path == "/tmp/review-report.json"

            screen._export_in_progress = True
            screen._export_token = 1
            screen._export_started_token = 1
            screen._finish_export_worker(MagicMock(state=WorkerState.ERROR))

            screen._export_in_progress = True
            screen._export_token = 1
            screen._export_started_token = 1
            screen._finish_export_worker(MagicMock(state=WorkerState.CANCELLED))

            screen._export_in_progress = True
            screen._export_token = 9
            screen._export_started_token = 1
            screen._finish_export_worker(success)

            screen._export_in_progress = False
            screen._finish_export_worker(success)

            screen._export_in_progress = True
            screen._export_token = 1
            screen._export_started_token = 1
            screen._finish_export_worker(MagicMock(state=WorkerState.SUCCESS, result="bad"))

            screen._saved_report_path = "/tmp/already.json"
            screen._save_session_report()

            screen._saved_report_path = None
            screen._export_in_progress = True
            screen._save_session_report()

            done = Worker.StateChanged(success, WorkerState.SUCCESS)
            screen.on_export_session_report_worker_state_changed(done)

            event = Worker.StateChanged(MagicMock(state=WorkerState.RUNNING), WorkerState.RUNNING)
            screen.on_export_session_report_worker_state_changed(event)
            await pilot.pause()

    asyncio.run(_run())
