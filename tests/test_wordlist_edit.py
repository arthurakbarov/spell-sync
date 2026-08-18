"""Unit tests for additive wordlist edits."""

from pathlib import Path

import pytest

from spell_sync.application.wordlist_edit import (
    append_words_guarded,
    append_words_to_wordlist,
    parse_word_lines,
)
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.operation_lock import acquire_operation_lock


def test_parse_word_lines_skips_junk() -> None:
    accepted, rejected = parse_word_lines("Alpha\n\n!!!\nbeta\nAlpha\n")
    assert accepted == ("Alpha", "beta")
    assert rejected == ("!!!",)


def test_parse_word_lines_rejects_phrases() -> None:
    accepted, rejected = parse_word_lines("New York\none\n")
    assert accepted == ("one",)
    assert rejected == ("New York",)


def test_append_words_to_wordlist_additive(tmp_path: Path) -> None:
    path = tmp_path / "wordlist.txt"
    write_text_words(str(path), ["alpha"], "utf-8", False, quiet=True)
    result = append_words_to_wordlist(path, "beta\nalpha\n")
    assert result.added == ("beta",)
    assert result.already_present == ("alpha",)
    assert path.read_text(encoding="utf-8").splitlines() == ["alpha", "beta"]


def test_cmd_add_unreadable_wordlist_is_not_a_write_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from spell_sync.cli_options import CliOptions
    from spell_sync.commands import cmd_add
    from spell_sync.guest_messages import WORD_LIST_UNREADABLE

    path = tmp_path / "wordlist.txt"
    path.write_text("alpha\x00\n", encoding="utf-8")
    code = cmd_add(CliOptions(wordlist=str(path), add_words=["beta"], json_output=True))
    assert code == int(ExitCode.WORDLIST_UNREADABLE)
    payload = json.loads(capsys.readouterr().out)
    assert payload["message"] == WORD_LIST_UNREADABLE
    assert "write" not in payload["message"]
    assert path.read_text(encoding="utf-8") == "alpha\x00\n"


def test_append_words_refuses_undecodable_wordlist(tmp_path: Path) -> None:
    path = tmp_path / "wordlist.txt"
    path.write_bytes(b"old\x98word\n")
    with pytest.raises(OSError, match="word list is unreadable"):
        append_words_to_wordlist(path, "newword\n")
    assert path.read_bytes() == b"old\x98word\n"


def test_wordlist_unreadable_detects_undecodable_bytes(tmp_path: Path) -> None:
    from spell_sync.io import wordlist_unreadable

    path = tmp_path / "wordlist.txt"
    path.write_bytes(b"\x98")
    assert wordlist_unreadable(path) is True


def test_wordlist_unreadable_detects_control_bytes(tmp_path: Path) -> None:
    from spell_sync.io import wordlist_unreadable

    path = tmp_path / "wordlist.txt"
    path.write_bytes(b"good\n\x00bad\n")
    assert wordlist_unreadable(path) is True


def test_append_words_guarded_respects_lock(tmp_path: Path) -> None:
    path = tmp_path / "wordlist.txt"
    write_text_words(str(path), ["alpha"], "utf-8", False, quiet=True)
    with acquire_operation_lock(path, "push"):
        result = append_words_guarded(path, "beta\n")
    assert result == int(ExitCode.PUSH_ABORT)
    assert path.read_text(encoding="utf-8").splitlines() == ["alpha"]
