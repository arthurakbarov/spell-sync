"""Immutable prepared push: one plan for confirm, dry-run, and execute."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .exit_codes import ExitCode
from .io import atomic_write
from .log import log
from .neovim_mkspell import mkspell_after_neovim_writes
from .push_abort import PushAbort, handle_failed_push_rollback
from .push_journal import PushJournalSession, file_content_hash
from .push_plan import (
    PlannedTarget,
    PushPlan,
    fingerprint_conflict,
    max_removals_in_plan,
)
from .push_render import RenderedWrite, render_dictionary, render_wordlist
from .push_setup import (
    make_push_result,
    prepare_writable_dictionaries,
    wordlist_needs_rewrite,
)
from .push_transaction import PushTransaction
from .sync_models import PushResult

if TYPE_CHECKING:
    from .sync_context import RuntimeContext


@dataclass(frozen=True)
class PreparedTarget:
    planned: PlannedTarget
    rendered: RenderedWrite


@dataclass(frozen=True)
class PreparedPush:
    ctx: RuntimeContext
    plan: PushPlan
    targets: tuple[PreparedTarget, ...]
    dictionaries: tuple
    skipped_unreadable: tuple[str, ...]
    skipped_corrupt: tuple[str, ...]
    skipped_blocked: tuple[str, ...]
    wordlist_rendered: RenderedWrite | None
    wordlist_needs_write: bool

    @property
    def words(self):
        return self.plan.words

    def max_removals(self) -> int:
        return max_removals_in_plan(self.plan)


def _render_plan(plan: PushPlan) -> tuple[PreparedTarget, ...]:
    rendered: list[PreparedTarget] = []
    for target in plan.targets:
        payload = render_dictionary(target.dictionary, plan.words)
        rendered.append(PreparedTarget(target, payload))
    return tuple(rendered)


def prepare_push(
    ctx: RuntimeContext,
    words,
    *,
    skip_names: frozenset[str] | None = None,
) -> PreparedPush | ExitCode:
    from .push_setup import setup_push

    setup = setup_push(ctx, words, skip_names=skip_names)
    if isinstance(setup, ExitCode):
        return setup
    plan = setup.plan
    needs_write = wordlist_needs_rewrite(ctx, words)
    wl_rendered = render_wordlist(words) if needs_write else None
    return PreparedPush(
        ctx=ctx,
        plan=plan,
        targets=_render_plan(plan),
        dictionaries=tuple(setup.dictionaries),
        skipped_unreadable=tuple(setup.skipped_unreadable),
        skipped_corrupt=tuple(setup.skipped_corrupt),
        skipped_blocked=tuple(setup.skipped_blocked),
        wordlist_rendered=wl_rendered,
        wordlist_needs_write=needs_write,
    )


def plan_fingerprint_conflict(prepared: PreparedPush) -> str | None:
    """Return dictionary name when on-disk content diverged from the frozen plan."""
    for item in prepared.targets:
        if fingerprint_conflict(item.planned.dictionary, item.planned.read_result):
            return item.planned.dictionary.name
    return None


def write_rendered(path: Path, rendered: RenderedWrite) -> bool:
    try:
        atomic_write(path, rendered.payload)
    except OSError as exc:
        log.warn(f"no write access {path}: {exc}")
        return False
    actual = file_content_hash(path)
    return actual == rendered.sha256


def execute_prepared_push(
    prepared: PreparedPush,
    *,
    dry_run: bool,
    running_app_skip_reasons_fn,
) -> PushResult | ExitCode | PushAbort:
    ctx = prepared.ctx
    conflict = plan_fingerprint_conflict(prepared)
    if conflict is not None:
        log.abort(f"push aborted — {conflict} changed after plan (fingerprint conflict).")
        return ExitCode.PUSH_ABORT

    tx = PushTransaction.begin(ctx.wordlist_file, list(prepared.dictionaries), dry_run=dry_run)
    journal_session: PushJournalSession | None = None
    try:
        prep = prepare_writable_dictionaries(ctx, tx, list(prepared.dictionaries))
        if isinstance(prep, ExitCode):
            return prep
        writable, skipped_backup = prep
        if dry_run:
            written = tuple(d.name for d in writable)
            return make_push_result(
                ctx,
                prepared.words,
                list(prepared.skipped_unreadable),
                list(prepared.skipped_corrupt),
                list(prepared.skipped_blocked),
                skipped_backup,
                set(),
                written,
            )

        journal_session = PushJournalSession.begin(
            ctx.wordlist_file,
            command="push",
            tx=tx,
            dictionaries=writable,
        )

        if prepared.wordlist_needs_write and prepared.wordlist_rendered is not None:
            try:
                journal_session.mark_wordlist_write_started(prepared.wordlist_rendered.sha256)
            except OSError:
                return handle_failed_push_rollback(
                    tx,
                    journal_session,
                    reason="journal_update_failed",
                    message="push aborted — failed to update push journal.",
                    journal_update_failed=True,
                )
            tx.mark_wordlist_write_started()
            if not write_rendered(ctx.wordlist_file, prepared.wordlist_rendered):
                return handle_failed_push_rollback(
                    tx,
                    journal_session,
                    reason="wordlist_write_failed",
                    message="push aborted — failed to write wordlist.",
                )
            try:
                journal_session.mark_wordlist_write_completed()
            except OSError:
                return handle_failed_push_rollback(
                    tx,
                    journal_session,
                    reason="journal_update_failed",
                    message="push aborted — failed to update push journal.",
                    journal_update_failed=True,
                )
            tx.mark_wordlist_write_completed()

        skipped_late_running: set[str] = set()
        skipped_running_details: dict[str, str] = {}
        late_reasons = running_app_skip_reasons_fn([d.name for d in writable])
        outcomes: list[tuple[str, bool]] = []
        prepared_by_name = {t.planned.dictionary.name: t for t in prepared.targets}

        for dictionary in writable:
            if dictionary.name in late_reasons:
                reason = late_reasons.get(dictionary.name)
                if reason:
                    log.warn(f"  {dictionary.name}: {reason} — push skipped")
                    skipped_running_details[dictionary.name] = reason
                skipped_late_running.add(dictionary.name)
                continue
            item = prepared_by_name.get(dictionary.name)
            if item is None:
                continue
            if fingerprint_conflict(dictionary, item.planned.read_result):
                return handle_failed_push_rollback(
                    tx,
                    journal_session,
                    reason="fingerprint_conflict",
                    message=(
                        f"push aborted — {dictionary.name} changed after plan "
                        "(fingerprint conflict)."
                    ),
                )
            try:
                journal_session.mark_write_started(dictionary.name, item.rendered.sha256)
            except OSError:
                return handle_failed_push_rollback(
                    tx,
                    journal_session,
                    reason="journal_update_failed",
                    message="push aborted — failed to update push journal.",
                    journal_update_failed=True,
                )
            tx.mark_write_started(dictionary)
            ok = write_rendered(Path(dictionary.path), item.rendered)
            outcomes.append((dictionary.name, ok))
            if ok:
                tx.mark_write_completed(dictionary)
                try:
                    journal_session.mark_target_written(dictionary.name)
                except OSError:
                    return handle_failed_push_rollback(
                        tx,
                        journal_session,
                        reason="journal_update_failed",
                        message="push aborted — failed to update push journal.",
                        journal_update_failed=True,
                    )
            else:
                return handle_failed_push_rollback(
                    tx,
                    journal_session,
                    reason="dictionary_write_failed",
                    message=f"push aborted — not written: {dictionary.name}",
                )

        written = tuple(name for name, ok in outcomes if ok)
        mkspell_after_neovim_writes(written)
        try:
            journal_session.complete()
        except OSError:
            return handle_failed_push_rollback(
                tx,
                journal_session,
                reason="journal_update_failed",
                message="push aborted — failed to finalize push journal.",
                journal_update_failed=True,
            )
        tx.discard_snapshots()
        return make_push_result(
            ctx,
            prepared.words,
            list(prepared.skipped_unreadable),
            list(prepared.skipped_corrupt),
            list(prepared.skipped_blocked),
            skipped_backup,
            skipped_late_running,
            written,
            running_details=skipped_running_details,
        )
    finally:
        tx.close()
