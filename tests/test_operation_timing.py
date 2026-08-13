"""Product operation duration estimates."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from spell_sync import operation_timing as timing


class TestOperationTiming(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store = Path(self._tmp.name) / "operation-timing.json"
        timing.set_timing_store_path(store)
        self.addCleanup(lambda: timing.set_timing_store_path(None))

    def test_eta_line_threshold(self) -> None:
        self.assertIsNone(timing.eta_line("dashboard"))
        self.assertEqual(
            timing.eta_line("history_load"),
            "Usually takes about 5 seconds.",
        )
        self.assertIn("seconds", timing.eta_line("push") or "")

    def test_eta_disabled_by_env(self) -> None:
        with patch.dict(os.environ, {"SPELL_SYNC_OPERATION_ETA": "0"}):
            self.assertIsNone(timing.eta_line("push"))

    def test_record_sample_blends_toward_median(self) -> None:
        initial = timing.expected_seconds("status")
        assert initial is not None
        for _ in range(10):
            timing.record_sample("status", 30.0)
        blended = timing.expected_seconds("status")
        assert blended is not None
        self.assertGreater(blended, initial)

    def test_format_minutes(self) -> None:
        self.assertIn("1 minute", timing.format_duration_hint(60))
        self.assertIn("2 minutes", timing.format_duration_hint(120))

    def test_hang_threshold_bounds(self) -> None:
        value = timing.hang_threshold_seconds("push")
        self.assertGreaterEqual(value, 15.0)
        self.assertLessEqual(value, 60.0)
        with patch.dict(os.environ, {"SPELL_SYNC_OPERATION_HANG": "0"}):
            self.assertEqual(timing.hang_threshold_seconds("push"), float("inf"))

    def test_load_samples_rejects_corrupt_and_invalid_entries(self) -> None:
        store = timing.timing_store_path()
        store.write_text("not json", encoding="utf-8")
        self.assertEqual(timing._load_samples(), {})
        store.write_text("[]", encoding="utf-8")
        self.assertEqual(timing._load_samples(), {})
        store.write_text(
            '{"status": "bad", "push": [0, -1, "x", null]}',
            encoding="utf-8",
        )
        samples = timing._load_samples()
        self.assertNotIn("status", samples)
        self.assertNotIn("push", samples)

    def test_save_samples_oserror_is_ignored(self) -> None:
        store = timing.timing_store_path()
        with patch.object(type(store), "write_text", side_effect=OSError("denied")):
            timing._save_samples({"push": [1.0]})
        self.assertFalse(store.is_file())

    def test_expected_seconds_unknown_key_uses_median(self) -> None:
        key = "coverage_only_timing_key"
        timing.record_sample(key, 12.0)
        timing.record_sample(key, 14.0)
        self.assertEqual(timing.expected_seconds(key), 13)

    def test_record_sample_skips_invalid(self) -> None:
        store = timing.timing_store_path()
        timing.record_sample("", 5.0)
        timing.record_sample("push", -1.0)
        timing.record_sample("push", float("nan"))
        if store.is_file():
            data = json.loads(store.read_text(encoding="utf-8"))
            self.assertNotIn("", data)
        else:
            self.assertFalse(store.is_file())

    def test_expected_seconds_unknown_key_no_samples(self) -> None:
        self.assertIsNone(timing.expected_seconds("coverage_unknown_operation_key"))

    def test_eta_line_below_threshold_after_blend(self) -> None:
        for _ in range(20):
            timing.record_sample("version", 0.5)
        self.assertIsNone(timing.eta_line("version"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
