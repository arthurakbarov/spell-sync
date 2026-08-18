"""Multi-line ``Label: value`` blocks must share one value column.

Regression: Review complete / Status used hand-rolled f-strings so shorter labels
sat left of longer ones. Substring checks like ``"Project: /path"`` do not verify
alignment across a block.

Also fail if product modules introduce adjacent hand-rolled ``f"Label: {...}"``
field lines instead of ``format_aligned_fields`` / ``format_indented_fields``.
"""

import re
import tempfile
import unittest
from datetime import UTC
from pathlib import Path

from spell_sync.application.field_blocks import (
    field_block_alignment_errors,
    format_aligned_fields,
)
from spell_sync.application.product_concepts import COLLECT_WORDS_LABEL, UPDATE_APPS_LABEL
from spell_sync.application.push_preview_copy import format_push_preview_summary
from spell_sync.application.review_session import ReviewSession, build_review_session_report
from spell_sync.application.session_report_export import (
    SessionReportExport,
    export_session_report,
)
from spell_sync.application.status_copy import format_status_summary
from spell_sync.application.support_report import (
    InstallationInfo,
    PrivacyManifest,
    ProjectSupportState,
    RecoverySupportState,
    SupportReport,
    format_support_report_text,
)
from spell_sync.application.target_details import (
    TargetDetailsSnapshot,
    format_target_details_text,
)
from spell_sync.operation_reports import StatusDetailSnapshot
from tests.tui.fake_service import sample_preview

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_GUEST_SOURCE_ROOTS = (
    _PACKAGE_ROOT / "spell_sync" / "application",
    _PACKAGE_ROOT / "spell_sync" / "tui",
)
# Adjacent guest-looking field f-strings — the pattern humans keep pasting.
_ADJACENT_FIELD_FSTRINGS = re.compile(
    r"""f["']([A-Za-z][^"']{0,48}): \{[^}]+\}["']\s*,?\s*\n\s*f["']([A-Za-z][^"']{0,48}): \{""",
    re.M,
)


def assert_guest_field_blocks_aligned(text: str) -> None:
    errors = field_block_alignment_errors(text)
    if errors:
        preview = "\n".join(text.splitlines()[:24])
        raise AssertionError(
            "guest field-block contract violated:\n- "
            + "\n- ".join(errors)
            + f"\n\ntext:\n{preview}"
        )


# Allowlist: modules that only re-export or document the pattern in comments/tests.
_SCAN_ALLOWLIST = frozenset(
    {
        "spell_sync/application/field_blocks.py",
    }
)


class TestFieldBlockFormatter(unittest.TestCase):
    def test_pad_after_colon_aligns_values(self) -> None:
        lines = format_aligned_fields(
            [
                (COLLECT_WORDS_LABEL, "Skipped"),
                (UPDATE_APPS_LABEL, "Skipped"),
            ]
        )
        self.assertEqual(
            lines,
            [
                "Collect my words: Skipped",
                "Update my apps:   Skipped",
            ],
        )
        assert_guest_field_blocks_aligned("\n".join(lines))

    def test_detector_flags_unaligned_hand_roll(self) -> None:
        bad = "Collect my words: Skipped\nUpdate my apps: Skipped"
        errors = field_block_alignment_errors(bad)
        self.assertTrue(errors)
        with self.assertRaises(AssertionError):
            assert_guest_field_blocks_aligned(bad)


class TestGuestFieldBlockProducers(unittest.TestCase):
    """Canonical producers — extend when adding multi-line Label: value blocks."""

    def test_review_session_report_aligned(self) -> None:
        report = build_review_session_report(ReviewSession(pull_skipped=True, push_skipped=True))
        text = "\n".join(report.summary_lines)
        assert_guest_field_blocks_aligned(text)
        self.assertRegex(text, r"Collect my words:\s+Skipped")
        self.assertRegex(text, r"Update my apps:\s+Skipped")

    def test_push_preview_summary_aligned(self) -> None:
        text = format_push_preview_summary(sample_preview())
        assert_guest_field_blocks_aligned(text)

    def test_session_report_text_export_aligned(self) -> None:
        export = SessionReportExport(
            schema_version=1,
            generated_at="2026-01-01T00:00:00Z",
            spell_sync_version="0.0.0",
            pull_status="Skipped",
            push_status="Skipped",
            recovery_note="No recovery is required.",
            pull_planned_additions=None,
            pull_actual_additions=None,
            pull_skipped_sources=None,
            push_planned_updates=None,
            push_actual_updates=None,
            push_skipped_targets=None,
            recovery_required=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.txt"
            export_session_report(export, output_path=path, fmt="text")
            text = path.read_text(encoding="utf-8")
        assert_guest_field_blocks_aligned(text)

    def test_target_details_aligned(self) -> None:
        details = TargetDetailsSnapshot(
            identifier="chrome",
            display_name="Chrome",
            profile_label="Default",
            enabled=True,
            detected=True,
            readable=True,
            writable=True,
            runtime_state="Ready",
            pull_supported=True,
            push_supported=True,
            filtering_label="Applicable Latin-script personal words",
            profile_model="Chromium profile",
            close_policy_label="No running-application block",
            recovery_protected=True,
            discovery_source="Chromium profile discovery",
            custom_dictionary_path="/tmp/Custom Dictionary.txt",
            automated_validation="Covered",
            manual_validation="Recorded",
            suggested_action=None,
            detail=None,
        )
        assert_guest_field_blocks_aligned(format_target_details_text(details))

    def test_status_summary_includes_warnings(self) -> None:
        text = format_status_summary(
            StatusDetailSnapshot(
                wordlist_path="/tmp/wordlist.txt",
                project_dir="/tmp/project",
                config_path=None,
                wordlist_count=1,
                targets=(),
                skipped_unreadable=(),
                skipped_corrupt=(),
                warnings=("Sublime Text User Preferences define added_words (2), which overrides",),
            )
        )
        self.assertIn("! Sublime Text User Preferences define added_words", text)

    def test_status_summary_aligned(self) -> None:
        text = format_status_summary(
            StatusDetailSnapshot(
                wordlist_path="/tmp/wordlist.txt",
                project_dir="/tmp/project",
                config_path="/tmp/spell-sync.toml",
                wordlist_count=1747,
                targets=(),
                skipped_unreadable=(),
                skipped_corrupt=(),
            )
        )
        assert_guest_field_blocks_aligned(text)
        self.assertRegex(text, r"Word list:\s+/tmp/wordlist\.txt")
        self.assertRegex(text, r"Project:\s+/tmp/project")
        self.assertRegex(text, r"Config:\s+/tmp/spell-sync\.toml")
        self.assertRegex(text, r"Words in your list:\s+1747")
        # Shorter labels pad after ':' so values share a column with the longest label.
        project_line = next(line for line in text.splitlines() if line.startswith("Project:"))
        words_line = next(
            line for line in text.splitlines() if line.startswith("Words in your list:")
        )
        self.assertEqual(
            project_line.index("/tmp/project"),
            words_line.index("1747"),
        )

    def test_support_report_text_aligned(self) -> None:
        from datetime import datetime

        report = SupportReport(
            schema_version=1,
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            spell_sync_version="1.0.0",
            python_version="3.12.0",
            operating_system="Darwin",
            architecture="arm64",
            installation=InstallationInfo("1.0.0", "test"),
            project=ProjectSupportState(True, 10, False),
            targets=(),
            recovery=RecoverySupportState(False, "absent"),
            recent_operations=(),
            notices=(),
            privacy=PrivacyManifest(),
        )
        assert_guest_field_blocks_aligned(format_support_report_text(report))


class TestGuestCopyUsesAsciiEllipsis(unittest.TestCase):
    """COPY_STYLE: never U+2026 in guest product modules."""

    _EXTRA_FILES = (
        "spell_sync/guest_messages.py",
        "spell_sync/log.py",
        "spell_sync/lint.py",
        "spell_sync/operation_presenter.py",
        "spell_sync/health/report.py",
        "spell_sync/subprocess_utils.py",
    )

    def test_guest_modules_do_not_contain_unicode_ellipsis(self) -> None:
        glyph = "\u2026"
        hits: list[str] = []
        paths = [path for root in _GUEST_SOURCE_ROOTS for path in root.rglob("*.py")]
        paths.extend(_PACKAGE_ROOT / rel for rel in self._EXTRA_FILES)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if glyph not in text:
                continue
            rel = path.relative_to(_PACKAGE_ROOT).as_posix()
            for index, line in enumerate(text.splitlines(), start=1):
                if glyph in line:
                    hits.append(f"{rel}:{index}")
        if hits:
            raise AssertionError(
                "Unicode ellipsis U+2026 in guest copy (use three ASCII periods):\n- "
                + "\n- ".join(hits)
            )


class TestNoHandRolledAdjacentFieldFStrings(unittest.TestCase):
    """Catch the Status / Review-complete class of bug at the source."""

    def test_product_modules_do_not_hand_roll_adjacent_field_fstrings(self) -> None:
        violations: list[str] = []
        for root in _GUEST_SOURCE_ROOTS:
            for path in sorted(root.rglob("*.py")):
                rel = path.relative_to(_PACKAGE_ROOT).as_posix()
                if rel in _SCAN_ALLOWLIST:
                    continue
                text = path.read_text(encoding="utf-8")
                for match in _ADJACENT_FIELD_FSTRINGS.finditer(text):
                    line = text[: match.start()].count("\n") + 1
                    violations.append(
                        f"{rel}:{line}: {match.group(1)!r} / {match.group(2)!r} "
                        f"(use format_aligned_fields / format_indented_fields)"
                    )
        if violations:
            raise AssertionError(
                "hand-rolled adjacent Label: value f-strings in product UI code:\n- "
                + "\n- ".join(violations)
            )


if __name__ == "__main__":
    unittest.main()
