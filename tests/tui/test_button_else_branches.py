"""Hit unused TUI button-handler else/exit arcs for publish branch coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

from textual.widgets import Button

from spell_sync.application.requests import ProjectRef
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.logs_screen import LogsScreen, TechnicalLogScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.pull_confirm_screen import PullConfirmScreen
from spell_sync.tui.screens.recovery_confirm_screen import RecoveryConfirmScreen
from spell_sync.tui.screens.setup_targets_screen import SetupTargetsScreen
from spell_sync.tui.screens.setup_welcome_screen import SetupWelcomeScreen
from spell_sync.tui.screens.status_screen import StatusScreen
from spell_sync.tui.screens.target_details_screen import TargetDetailsScreen
from spell_sync.tui.screens.target_settings_screen import TargetSettingsScreen
from tests.tui.fake_service import fake_service, sample_pull_preview, sample_recovery_preview


def _controller() -> TuiController:
    return TuiController(fake_service(), ProjectRef())


def _noop_press(screen: object) -> None:
    screen._app = MagicMock()  # type: ignore[attr-defined]
    handler = getattr(screen, "on_button_pressed", None)
    assert handler is not None
    handler(Button.Pressed(Button(id="coverage-noop")))


def test_button_handlers_ignore_unknown_ids() -> None:
    controller = _controller()
    screens: list[object] = [
        TargetDetailsScreen(controller, "chrome"),
        StatusScreen(controller),
        SetupWelcomeScreen(controller),
        SetupTargetsScreen(controller, "wordlist detail"),
        TargetSettingsScreen(controller),
        PullConfirmScreen(controller, sample_pull_preview()),
        RecoveryConfirmScreen(controller, sample_recovery_preview(), "recover"),
        PreviewScreen(controller),
        DashboardScreen(controller),
        LogsScreen(controller),
        TechnicalLogScreen(controller),
    ]
    for screen in screens:
        _noop_press(screen)
