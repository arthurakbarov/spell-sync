"""Machine-local active wordlist pointer and recent list."""

from pathlib import Path

import spell_sync.paths as paths_mod
import spell_sync.project_memory as memory


def _make_wordlist(directory: Path, name: str = "wordlist.txt") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("alpha\n", encoding="utf-8")
    return path.resolve()


def test_remember_and_list_recent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(memory, "_state_root_override", tmp_path / "state")
    first = _make_wordlist(tmp_path / "a")
    second = _make_wordlist(tmp_path / "b")
    memory.remember_wordlist(first)
    memory.remember_wordlist(second)
    assert memory.remembered_wordlist() == second
    recent = memory.list_recent_wordlists()
    assert recent[0] == second
    assert first in recent


def test_remembered_skips_missing_active(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(memory, "_state_root_override", tmp_path / "state")
    first = _make_wordlist(tmp_path / "a")
    second = _make_wordlist(tmp_path / "b")
    memory.remember_wordlist(first)
    memory.remember_wordlist(second)
    second.unlink()
    assert memory.remembered_wordlist() == first


def test_resolve_uses_pointer_when_cwd_has_no_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(memory, "_state_root_override", tmp_path / "state")
    wordlist = _make_wordlist(tmp_path / "project")
    (tmp_path / "project" / "spell-sync.toml").write_text(
        "[dictionaries]\neditors = true\n", encoding="utf-8"
    )
    memory.remember_wordlist(wordlist)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert paths_mod.resolve_wordlist_path(None) == wordlist


def test_resolve_prefers_cwd_project_over_pointer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(memory, "_state_root_override", tmp_path / "state")
    remembered = _make_wordlist(tmp_path / "remembered")
    memory.remember_wordlist(remembered)
    local = tmp_path / "local"
    local_wl = _make_wordlist(local)
    (local / "spell-sync.toml").write_text("[dictionaries]\neditors = true\n", encoding="utf-8")
    monkeypatch.chdir(local)
    assert paths_mod.resolve_wordlist_path(None) == local_wl


def test_corrupt_memory_is_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(memory, "_state_root_override", tmp_path / "state")
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "active-project.json").write_text("{not-json", encoding="utf-8")
    assert memory.remembered_wordlist() is None
    assert memory.list_recent_wordlists() == ()
