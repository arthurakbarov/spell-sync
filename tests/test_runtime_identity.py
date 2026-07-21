"""Runtime identity preview/execution consistency regressions."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from spell_sync.application.reports import OperationOutcome
from spell_sync.application.requests import ProjectRef, PullRequest, PushRequest
from spell_sync.application.service import SpellSyncService
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.paths import EDITOR_DICT_FILENAME
from spell_sync.push_journal import journal_path_for_wordlist
from spell_sync.runtime_identity import build_runtime_identity
from spell_sync.runtime_settings import RuntimeSettings
from spell_sync.target_capabilities import TargetFilterKind
from spell_sync.words import subset_english
from tests.runtime_helpers import make_runtime_context, make_sync_run


def _patch_discover(
    builder: Callable[[RuntimeSettings], list[Dictionary]] | list[Dictionary],
):
    if isinstance(builder, list):
        dictionaries = builder

        def _discover(_settings: RuntimeSettings) -> tuple[Dictionary, ...]:
            return tuple(dictionaries)

        side_effect = _discover
    else:

        def _discover(settings: RuntimeSettings) -> tuple[Dictionary, ...]:
            return tuple(builder(settings))

        side_effect = _discover
    return patch(
        "spell_sync.application._runtime_factory.discover_dictionaries",
        side_effect=side_effect,
    )


def _disabled_targets_config(*, editors: bool = False, strict: bool | None = None) -> str:
    lines = [
        "[dictionaries]",
        f"editors = {'true' if editors else 'false'}",
        "chrome = false",
        "edge = false",
        "brave = false",
        "vivaldi = false",
        "firefox = false",
        "neovim = false",
        "jetbrains = false",
        "hunspell = false",
        "obsidian = false",
        "libreoffice = false",
    ]
    if strict is not None:
        lines.extend(["", "[push]", f"strict = {'true' if strict else 'false'}"])
    return "\n".join(lines) + "\n"


def _disabled_targets_config_backup(*, backup_keep: int) -> str:
    return _disabled_targets_config(editors=True) + "\n[io]\n" + f"backup_keep = {backup_keep}\n"


class TestRuntimeIdentityPush(unittest.TestCase):
    def _cursor_setup(self, tmp: str) -> tuple[Path, Path, Path, SpellSyncService, PushRequest]:
        root = Path(tmp)
        wordlist = root / "wordlist.txt"
        wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
        config = root / "spell-sync.toml"
        config.write_text(_disabled_targets_config(editors=True), encoding="utf-8")
        cursor_dir = root / "cursor-user"
        cursor_dir.mkdir()
        cursor_dict = cursor_dir / EDITOR_DICT_FILENAME
        request = PushRequest(project=ProjectRef(wordlist=wordlist))
        return wordlist, config, cursor_dict, SpellSyncService(), request

    def test_push_target_disabled_after_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            editor = Dictionary("editor:cursor", str(cursor_dict), DictionaryFormat.TEXT)

            def _discover(settings: RuntimeSettings) -> list[Dictionary]:
                if settings.dictionaries.editors:
                    return [editor]
                return []

            with _patch_discover(_discover):
                preview = service.load_push_preview(request)
                self.assertIsNotNone(preview.prepared)
                target_names = {item.planned.dictionary.name for item in preview.prepared.targets}
                self.assertIn("editor:cursor", target_names)

                config.write_text(_disabled_targets_config(editors=False), encoding="utf-8")
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )

            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertIn("changed after the preview", execution.message.lower())
            self.assertFalse(cursor_dict.exists())
            self.assertFalse(journal_path_for_wordlist(wordlist).exists())

    def test_push_target_enabled_after_preview_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            config.write_text(_disabled_targets_config(editors=False), encoding="utf-8")
            editor = Dictionary("editor:cursor", str(cursor_dict), DictionaryFormat.TEXT)

            def _discover(settings: RuntimeSettings) -> list[Dictionary]:
                if settings.dictionaries.editors:
                    return [editor]
                return []

            with _patch_discover(_discover):
                preview = service.load_push_preview(request)
                self.assertIsNotNone(preview.prepared)
                target_names = {item.planned.dictionary.name for item in preview.prepared.targets}
                self.assertNotIn("editor:cursor", target_names)

                config.write_text(_disabled_targets_config(editors=True), encoding="utf-8")
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )

            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertFalse(cursor_dict.exists())

    def test_strict_policy_changed_blocks_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            config.write_text(
                _disabled_targets_config(editors=True, strict=False),
                encoding="utf-8",
            )
            dictionary = Dictionary("custom", str(Path(tmp) / "local.txt"), DictionaryFormat.TEXT)
            Path(dictionary.path).write_text("alpha\nbeta\n", encoding="utf-8")
            with _patch_discover([dictionary]):
                preview = service.load_push_preview(request)
                config.write_text(
                    _disabled_targets_config(editors=True, strict=True),
                    encoding="utf-8",
                )
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)

    def test_backup_policy_changed_blocks_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            config.write_text(_disabled_targets_config_backup(backup_keep=3), encoding="utf-8")
            dictionary = Dictionary("custom", str(Path(tmp) / "local.txt"), DictionaryFormat.TEXT)
            Path(dictionary.path).write_text("alpha\nbeta\n", encoding="utf-8")
            with _patch_discover([dictionary]):
                preview = service.load_push_preview(request)
                config.write_text(_disabled_targets_config_backup(backup_keep=7), encoding="utf-8")
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)

    def test_config_source_precedence_changed_blocks_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            home = Path(tmp) / "home"
            home.mkdir()
            home_config = home / ".config" / "spell-sync" / "spell-sync.toml"
            home_config.parent.mkdir(parents=True)
            home_config.write_text("[push]\nstrict = true\n", encoding="utf-8")
            dictionary = Dictionary("custom", str(Path(tmp) / "local.txt"), DictionaryFormat.TEXT)
            Path(dictionary.path).write_text("alpha\nbeta\n", encoding="utf-8")
            with patch.dict("os.environ", {"HOME": str(home)}):
                with _patch_discover([dictionary]):
                    preview = service.load_push_preview(request)
                    config.write_text("[push]\nstrict = false\n", encoding="utf-8")
                    execution = service.execute_push_preview(
                        request,
                        preview,
                        confirmed_plan_id=preview.plan_identifier,
                    )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)

    def test_config_removed_blocks_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            dictionary = Dictionary("custom", str(Path(tmp) / "local.txt"), DictionaryFormat.TEXT)
            Path(dictionary.path).write_text("alpha\nbeta\n", encoding="utf-8")
            with _patch_discover([dictionary]):
                preview = service.load_push_preview(request)
                config.unlink()
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)

    def test_unchanged_runtime_executes_successfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            dictionary = Dictionary("custom", str(Path(tmp) / "local.txt"), DictionaryFormat.TEXT)
            dict_path = Path(dictionary.path)
            dict_path.write_text("alpha\nbeta\n", encoding="utf-8")
            with _patch_discover([dictionary]):
                preview = service.load_push_preview(request)
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.COMPLETED)
            self.assertIn("alpha", dict_path.read_text(encoding="utf-8"))

    def test_dry_run_blocks_stale_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, config, cursor_dict, service, request = self._cursor_setup(tmp)
            cursor_dict.write_text("alpha\nbeta\n", encoding="utf-8")
            editor = Dictionary("editor:cursor", str(cursor_dict), DictionaryFormat.TEXT)

            def _discover(settings: RuntimeSettings) -> list[Dictionary]:
                if settings.dictionaries.editors:
                    return [editor]
                return []

            with _patch_discover(_discover):
                preview = service.load_push_preview(request)
                config.write_text(_disabled_targets_config(editors=False), encoding="utf-8")
                execution = service.execute_push_dry_run(request, preview)
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)


class TestRuntimeIdentityPull(unittest.TestCase):
    def test_pull_config_change_blocks_execution(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dictionary = root / "local.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dictionary.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
            config = root / "spell-sync.toml"
            config.write_text(_disabled_targets_config(editors=False), encoding="utf-8")
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("custom", str(dictionary), DictionaryFormat.TEXT)],
            )
            from spell_sync.application.builders import build_pull_preview

            preview = build_pull_preview(run)
            before = wordlist.read_text(encoding="utf-8")
            config.write_text(
                _disabled_targets_config(editors=True),
                encoding="utf-8",
            )
            request = PullRequest(project=ProjectRef(wordlist=wordlist))
            execution = service.execute_pull(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertEqual(wordlist.read_text(encoding="utf-8"), before)


class TestRuntimeIdentitySubsetPolicy(unittest.TestCase):
    def test_subset_policy_from_dictionary_filter_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary(
                "win-en",
                str(Path(tmp) / "win-en.txt"),
                DictionaryFormat.TEXT,
            )
            context = make_runtime_context(wordlist, dictionaries=[dictionary])
            identity = build_runtime_identity(context)
            self.assertEqual(identity.targets[0].subset_policy, TargetFilterKind.LATIN.value)

    def test_subset_policy_from_dictionary_subset_fn(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary(
                "custom-subset",
                str(Path(tmp) / "custom.txt"),
                DictionaryFormat.TEXT,
                subset=subset_english,
            )
            context = make_runtime_context(wordlist, dictionaries=[dictionary])
            identity = build_runtime_identity(context)
            self.assertEqual(identity.targets[0].subset_policy, "subset_english")


class TestRuntimeIdentityFingerprintConflict(unittest.TestCase):
    def test_fingerprint_conflict_still_blocks_after_identity_match(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            dict_path = Path(tmp) / "local.txt"
            wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
            dict_path.write_text("alpha\nbeta\n", encoding="utf-8")
            (wordlist.parent / "spell-sync.toml").write_text(
                _disabled_targets_config(editors=False),
                encoding="utf-8",
            )
            dictionary = Dictionary("custom", str(dict_path), DictionaryFormat.TEXT)
            with _patch_discover([dictionary]):
                request = PushRequest(project=ProjectRef(wordlist=wordlist))
                preview = service.load_push_preview(request)
                dict_path.write_text("changed-on-disk\n", encoding="utf-8")
                execution = service.execute_push_preview(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertEqual(execution.conflict_target, "custom")
            self.assertEqual(execution.result, ExitCode.PUSH_ABORT)


if __name__ == "__main__":
    unittest.main()
