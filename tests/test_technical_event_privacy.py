"""Privacy guards for technical events, history, and support reports."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from spell_sync.application.requests import (
    PrepareTargetSettingsUpdateRequest,
    ProjectRef,
    SupportReportRequest,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.application.support_report import format_support_report_text, support_report_to_dict
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.technical_logging import reset_logging_for_tests
from spell_sync.project_setup.discovery import SetupTarget, SetupTargetDiscovery
from spell_sync.project_setup.target_settings import TargetSettingsOutcome

SENSITIVE_WORD = "SENSITIVE_USER_WORD_7f3a"
SECRET_TOKEN = "secret-token-value"
PRIVATE_HOME = "/home/private-user"


def _assert_sentinels_absent(text: str) -> None:
    for token in (SENSITIVE_WORD, SECRET_TOKEN, PRIVATE_HOME):
        assert token not in text, f"leaked sensitive token: {token!r}"


def _mock_discovery(enabled: frozenset[str]) -> SetupTargetDiscovery:
    targets = (
        SetupTarget(
            identifier="chrome",
            display_name="Chrome",
            path=Path(f"{PRIVATE_HOME}/chrome.txt"),
            format_name="text",
            detected=True,
            available=True,
            readable=True,
            supported=True,
            enabled_by_default=True,
            selectable=True,
            word_count=3,
            status="ok",
            detail=None,
            enabled="chrome" in enabled,
        ),
        SetupTarget(
            identifier="edge",
            display_name="Edge",
            path=Path(f"{PRIVATE_HOME}/edge.txt"),
            format_name="text",
            detected=True,
            available=True,
            readable=True,
            supported=True,
            enabled_by_default=True,
            selectable=True,
            word_count=3,
            status="ok",
            detail=None,
            enabled="edge" in enabled,
        ),
    )
    return SetupTargetDiscovery(
        targets=targets,
        default_enabled=tuple(sorted(enabled)),
    )


@pytest.fixture
def sensitive_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "home" / "private-user"
    project.mkdir(parents=True)
    wordlist = project / "wordlist.txt"
    wordlist.write_text(f"{SENSITIVE_WORD}\n{SECRET_TOKEN}\nalpha\n", encoding="utf-8")
    config = project / "spell-sync.toml"
    config.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
    return wordlist, config


def test_technical_events_do_not_leak_sentinels(
    tmp_path: Path,
    sensitive_project: tuple[Path, Path],
) -> None:
    reset_logging_for_tests()
    wordlist, _config = sensitive_project
    state = resolve_app_state_paths(state_root=tmp_path / "state")
    service = SpellSyncService(state_paths=state, enable_file_logging=True)

    with patch(
        "spell_sync.project_setup.target_settings.discover_setup_targets",
        side_effect=lambda *, selected_targets=None, enabled_targets=None: _mock_discovery(
            enabled_targets or frozenset()
        ),
    ):
        prepared = service.prepare_target_settings_update(
            PrepareTargetSettingsUpdateRequest(
                project=ProjectRef(wordlist=wordlist),
                selected_target_ids=frozenset({"edge"}),
            )
        )
        execution = service.execute_target_settings_update(
            prepared,
            confirmed_update_id=prepared.update_id,
            event_sink=lambda _event: None,
        )
        report = service.build_target_settings_report(execution)

    assert execution.outcome == TargetSettingsOutcome.COMPLETED
    assert report.operation == "targets"

    log_text = (
        state.technical_log.read_text(encoding="utf-8") if state.technical_log.is_file() else ""
    )
    history_text = (
        state.history_file.read_text(encoding="utf-8") if state.history_file.is_file() else ""
    )
    support = service.load_support_report(
        SupportReportRequest(project=ProjectRef(wordlist=wordlist)),
    )
    support_json = json.dumps(support_report_to_dict(support), sort_keys=True)
    support_text = format_support_report_text(support)

    for blob in (log_text, history_text, support_json, support_text):
        _assert_sentinels_absent(blob)
