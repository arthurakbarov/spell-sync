"""CLI operation presenter lifecycle."""

import io
import json
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from spell_sync import operation_timing as timing
from spell_sync.application.events import EventId, EventSeverity, OperationKind, PresentedEvent
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.technical_logging import reset_logging_for_tests
from spell_sync.log import Log
from spell_sync.operation_presenter import OperationSession, OperationSpec, operation_session


class TestOperationPresenter(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        timing.set_timing_store_path(root / "operation-timing.json")
        self.addCleanup(lambda: timing.set_timing_store_path(None))
        self._state = resolve_app_state_paths(state_root=root / "state")
        reset_logging_for_tests()
        self.addCleanup(reset_logging_for_tests)

    def test_session_disabled_when_quiet(self) -> None:
        with operation_session(
            OperationSpec(key="status", title="status"),
            enabled=False,
        ) as session:
            self.assertIsNone(session)

    def test_intro_eta_progress_outcome(self) -> None:
        buf = io.StringIO()
        log = Log()
        with (
            patch.dict("os.environ", {"SPELL_SYNC_OPERATION_HANG": "0"}),
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
            operation_session(
                OperationSpec(
                    key="status",
                    title="status",
                    descriptions=("Compare dictionaries.",),
                ),
                log=log,
            ) as session,
        ):
            assert session is not None
            session.note("Checking targets.")
            session(
                PresentedEvent(
                    operation=OperationKind.STATUS,
                    event_id=EventId.PULL_VALIDATING,
                    severity=EventSeverity.INFO,
                    message="Reading word list",
                )
            )
            session.succeed("status complete")
        text = buf.getvalue()
        self.assertIn("=== status ===", text)
        self.assertIn("[info ] Compare dictionaries.", text)
        self.assertIn("Usually takes about", text)
        self.assertIn("· Checking targets.", text)
        self.assertIn("· Reading word list", text)
        self.assertIn("[done ] status complete", text)

    def test_session_writes_technical_lifecycle_and_timing(self) -> None:
        buf = io.StringIO()
        with (
            patch.dict("os.environ", {"SPELL_SYNC_OPERATION_HANG": "0"}),
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
            operation_session(
                OperationSpec(key="doctor", title="doctor"),
                log=Log(),
            ) as session,
        ):
            assert session is not None
            time.sleep(0.02)
            duration = session.elapsed_ms
            session.succeed("doctor ok")
        self.assertGreaterEqual(duration, 1)
        log_text = self._state.technical_log.read_text(encoding="utf-8")
        self.assertIn('"eventId":"operation.started"', log_text)
        self.assertIn('"eventId":"operation.completed"', log_text)
        self.assertIn('"operation":"doctor"', log_text)
        samples = json.loads(timing.timing_store_path().read_text(encoding="utf-8"))
        self.assertIn("doctor", samples)
        self.assertGreater(samples["doctor"][-1], 0)

    def test_fail_writes_failed_bookend_without_timing_sample(self) -> None:
        buf = io.StringIO()
        with (
            patch.dict("os.environ", {"SPELL_SYNC_OPERATION_HANG": "0"}),
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
            operation_session(
                OperationSpec(key="lint", title="lint"),
                log=Log(),
            ) as session,
        ):
            assert session is not None
            session.fail("lint blocked")
        log_text = self._state.technical_log.read_text(encoding="utf-8")
        self.assertIn('"eventId":"operation.failed"', log_text)
        self.assertFalse(timing.timing_store_path().is_file())

    def test_success_and_error_events_do_not_duplicate_outcome(self) -> None:
        buf = io.StringIO()
        log = Log()
        session = OperationSession(
            OperationSpec(key="pull", title="pull"),
            log=log,
            record_timing=False,
        )
        with (
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
        ):
            session.start()
            session(
                PresentedEvent(
                    operation=OperationKind.PULL,
                    event_id=EventId.PULL_COMPLETED,
                    severity=EventSeverity.SUCCESS,
                    message="should not print as progress",
                )
            )
            session.succeed("wordlist updated")
        text = buf.getvalue()
        self.assertNotIn("should not print as progress", text)
        self.assertIn("[done ] wordlist updated", text)

    def test_empty_and_duplicate_events_and_notes(self) -> None:
        buf = io.StringIO()
        session = OperationSession(
            OperationSpec(key="pull", title="pull"),
            log=Log(),
            record_timing=False,
        )
        empty = PresentedEvent(
            operation=OperationKind.PULL,
            event_id=EventId.PULL_VALIDATING,
            severity=EventSeverity.INFO,
            message="   ",
        )
        event = PresentedEvent(
            operation=OperationKind.PULL,
            event_id=EventId.PULL_VALIDATING,
            severity=EventSeverity.INFO,
            message="Reading",
        )
        warn = PresentedEvent(
            operation=OperationKind.PULL,
            event_id=EventId.PULL_BLOCKED,
            severity=EventSeverity.WARNING,
            message="Blocked",
        )
        with (
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
        ):
            session.start()
            session(empty)
            session.note("")
            session.note("once")
            session(event)
            session(event)
            session(warn)
            session.succeed("ok")
        text = buf.getvalue()
        self.assertIn("· once", text)
        self.assertEqual(text.count("· Reading"), 1)
        self.assertIn("[WARN] Blocked", text)

    def test_outcome_kinds(self) -> None:
        buf = io.StringIO()
        session = OperationSession(
            OperationSpec(key="push", title="push"),
            log=Log(),
            record_timing=False,
        )
        with (
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
        ):
            session.start()
            session.warn_outcome("soft")
        self.assertIn("[WARN] soft", buf.getvalue())

        buf2 = io.StringIO()
        session2 = OperationSession(
            OperationSpec(key="push", title="push"),
            log=Log(),
            record_timing=False,
        )
        with (
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf2),
        ):
            session2.start()
            session2.fail("hard")
        self.assertIn("[ERROR] hard", buf2.getvalue())

        buf3 = io.StringIO()
        session3 = OperationSession(
            OperationSpec(key="push", title="push"),
            log=Log(),
            record_timing=False,
        )
        with (
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf3),
        ):
            session3.start()
            session3.abort("stopped")
            session3.abort("ignored")
        self.assertIn("[ABORT] stopped", buf3.getvalue())

    def test_start_without_eta_hint(self) -> None:
        buf = io.StringIO()
        with (
            patch("spell_sync.operation_presenter.eta_line", return_value=None),
            patch.dict("os.environ", {"SPELL_SYNC_OPERATION_HANG": "0"}),
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
            operation_session(
                OperationSpec(key="dashboard", title="dashboard"),
                log=Log(),
                record_timing=False,
            ) as session,
        ):
            assert session is not None
            session.succeed("ok")
        self.assertNotIn("Usually takes", buf.getvalue())

    def test_quiet_log_skips_timing_sample(self) -> None:
        quiet = Log(quiet=True)
        session = OperationSession(
            OperationSpec(key="status", title="status"),
            log=quiet,
            record_timing=True,
        )
        with (
            patch.dict("os.environ", {"SPELL_SYNC_OPERATION_HANG": "0"}),
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
        ):
            session.start()
            session.succeed("ok")
        store = timing.timing_store_path()
        self.assertFalse(store.is_file())

    def test_hang_watch_heartbeat(self) -> None:
        buf = io.StringIO()
        with (
            patch("spell_sync.operation_presenter.hang_threshold_seconds", return_value=0.05),
            patch(
                "spell_sync.operation_lifecycle.resolve_app_state_paths",
                return_value=self._state,
            ),
            redirect_stdout(buf),
            operation_session(
                OperationSpec(
                    key="push",
                    title="push",
                    activity="Update my apps",
                ),
                log=Log(),
                record_timing=False,
            ) as session,
        ):
            assert session is not None
            time.sleep(2.5)
            session.succeed("done")
        text = buf.getvalue()
        self.assertIn("Still working on Update my apps", text)
        self.assertNotIn("Still working on push…", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
