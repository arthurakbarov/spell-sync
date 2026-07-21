"""Evidence tests for diagnostic log redaction."""

from __future__ import annotations

from pathlib import Path

from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.safe_log import (
    safe_repr,
    sanitize_exception_message,
    sanitize_log_message,
)
from spell_sync.diagnostics.technical_logging import configure_file_logging, reset_logging_for_tests


def test_multiline_exception_redaction() -> None:
    text = "RuntimeError: token=abc123\n  File /Users/me/secret.txt\nwordlist content: alpha"
    cleaned = sanitize_log_message(text)
    assert "abc123" not in cleaned
    assert "alpha" not in cleaned
    assert "/Users/me" not in cleaned


def test_nested_and_chained_exception_messages() -> None:
    assert sanitize_exception_message("password=hunter2") == "[sanitized exception message]"
    assert sanitize_exception_message("plain operational note") == "[sanitized exception message]"


def test_unicode_and_secrets_redacted() -> None:
    message = "API token=ßëcret🔑 removed words: [café]"
    cleaned = sanitize_log_message(message)
    assert "ßëcret" not in cleaned
    assert "café" not in cleaned


def test_toml_fragment_redacted() -> None:
    fragment = "spell-sync.toml [chrome = true]"
    cleaned = sanitize_log_message(fragment)
    assert "chrome = true" not in cleaned.lower() or "[redacted]" in cleaned


def test_object_repr_with_secret() -> None:
    class SecretBox:
        def __repr__(self) -> str:
            return "SecretBox(token=super-secret)"

    assert "super-secret" not in safe_repr(SecretBox())


def test_format_safe_log_record_preserves_structured_event_line() -> None:
    import logging

    from spell_sync.diagnostics.safe_log import format_safe_log_record

    record = logging.LogRecord(
        name="spell_sync",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='{"eventId":"push.completed"}',
        args=(),
        exc_info=None,
    )
    record.structured_event = True
    assert (
        format_safe_log_record(record, "ignored prefix")
        == "ignored prefix"
    )


def test_format_safe_log_record_strips_traceback_message(tmp_path: Path) -> None:
    reset_logging_for_tests()
    paths = resolve_app_state_paths(state_root=tmp_path / "state")
    configure_file_logging(paths)
    import logging

    logger = logging.getLogger("spell_sync")
    try:
        raise RuntimeError("token=deadbeef wordlist content: beta")
    except RuntimeError:
        logger.error("push failed", exc_info=True)
    text = paths.technical_log.read_text(encoding="utf-8")
    assert "deadbeef" not in text
    assert "beta" not in text
    assert "exception_type=RuntimeError" in text
