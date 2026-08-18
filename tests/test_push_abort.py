"""Push rollback-failure handling."""

import unittest
from unittest.mock import MagicMock

from spell_sync.exit_codes import ExitCode
from spell_sync.push_abort import handle_failed_push_rollback
from spell_sync.push_transaction import RollbackResult


class TestPushAbortCoverage(unittest.TestCase):
    def test_rollback_paths(self):
        tx = MagicMock()
        tx.rollback.return_value = RollbackResult((), ("a",), ())
        session = MagicMock()
        session.mark_rollback_incomplete.side_effect = OSError("nope")
        abort = handle_failed_push_rollback(
            tx,
            session,
            reason="dictionary_write_failed",
            message="failed",
        )
        self.assertEqual(abort.reason, "rollback_incomplete")

        tx.rollback.return_value = RollbackResult(("a",), (), ())
        session.discard.side_effect = OSError("nope")
        abort2 = handle_failed_push_rollback(tx, session, reason="x", message="msg")
        self.assertEqual(abort2.exit_code, ExitCode.PUSH_ABORT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
