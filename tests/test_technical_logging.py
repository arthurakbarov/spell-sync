"""Technical logging tests."""

from pathlib import Path

from spell_sync.application.service import SpellSyncService
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.diagnostics.safe_log import sanitize_exception_message
from spell_sync.diagnostics.technical_logging import (
    configure_file_logging,
    get_spell_sync_logger,
    read_technical_log_tail,
    reset_logging_for_tests,
)


def _paths(tmp_path: Path):
    return resolve_app_state_paths(state_root=tmp_path / "state")


def setup_function() -> None:
    reset_logging_for_tests()


def teardown_function() -> None:
    reset_logging_for_tests()


def test_platform_paths_absolute(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    assert paths.state_directory.is_absolute()
    assert paths.history_file.is_absolute()
    assert paths.technical_log.is_absolute()


def test_idempotent_handler_setup(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    first = configure_file_logging(paths)
    second = configure_file_logging(paths)
    assert first.ok and second.ok
    logger = get_spell_sync_logger()
    file_handlers = [
        handler
        for handler in logger.handlers
        if handler.__class__.__name__ == "RotatingFileHandler"
    ]
    assert len(file_handlers) == 1


def test_log_file_created_on_write(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    configure_file_logging(paths)
    get_spell_sync_logger().info("push started", extra={"operation": "push"})
    assert paths.technical_log.is_file()
    snapshot = read_technical_log_tail(paths)
    assert any("push started" in line for line in snapshot.lines)


def test_missing_log_returns_empty(tmp_path: Path) -> None:
    snapshot = read_technical_log_tail(_paths(tmp_path))
    assert snapshot.lines == ()


def test_invalid_utf8_is_replaced(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.technical_log.parent.mkdir(parents=True, exist_ok=True)
    paths.technical_log.write_bytes(b"\xff\xfehello\n")
    snapshot = read_technical_log_tail(paths)
    assert snapshot.lines


def test_sanitized_exception_message() -> None:
    secret = "token=abc123"
    cleaned = sanitize_exception_message(f"failed with {secret}")
    assert "abc123" not in (cleaned or "")


def test_logger_does_not_write_to_stdout(tmp_path: Path, capsys) -> None:
    configure_file_logging(_paths(tmp_path))
    get_spell_sync_logger().info("background event")
    captured = capsys.readouterr()
    assert "background event" not in captured.out
    assert "background event" not in captured.err
    assert _paths(tmp_path).technical_log.is_file()


def test_service_read_technical_log_tail(tmp_path: Path) -> None:
    service = SpellSyncService(state_paths=_paths(tmp_path), enable_file_logging=True)
    get_spell_sync_logger().info("setup conflict detected")
    snapshot = service.read_technical_log_tail(max_lines=50)
    assert snapshot.path == service.technical_log_path()


def test_log_rotation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    configure_file_logging(paths)
    logger = get_spell_sync_logger()
    for index in range(200):
        logger.info("line-%s %s", index, "x" * 200)
    assert paths.technical_log.is_file()
    backups = list(paths.technical_log.parent.glob("spell-sync.log.*"))
    assert backups or paths.technical_log.stat().st_size <= 1024 * 1024


def test_sanitize_log_message_redacts_words_and_secrets() -> None:
    from spell_sync.diagnostics.safe_log import sanitize_log_message

    cleaned = sanitize_log_message("removed words: [bad] token=abc123")
    assert "abc123" not in cleaned
    assert "removed words" not in cleaned.lower()


def test_exception_logged_without_secret(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    configure_file_logging(paths)
    logger = get_spell_sync_logger()
    secret = "super-secret-token-value"
    try:
        raise RuntimeError(f"boom {secret}")
    except RuntimeError:
        logger.error("push failed", exc_info=True)
    text = paths.technical_log.read_text(encoding="utf-8")
    assert secret not in text
