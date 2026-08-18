"""Open the next guest operation without dropping the current context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .operational import OPERATIONAL_EXCEPTIONS

if TYPE_CHECKING:
    from textual.app import App

    from ..application.reports import PullPreview
    from .controller import TuiController


def wordlist_ready_for_update(controller: TuiController) -> bool:
    """False when status cannot be read or Update would abort on an empty list."""
    try:
        snapshot = controller.status()
    except OPERATIONAL_EXCEPTIONS:
        return False
    return (
        snapshot.wordlist_error is None
        and bool(snapshot.wordlist_count)
        and not snapshot.empty_wordlist
    )


def continue_to_update_apps(
    app: App[object],
    controller: TuiController,
    *,
    replace_current: bool = False,
) -> None:
    """Open Update preview. An active Review session stays on the Review Update step.

    ``replace_current`` pops this screen first (Extra words / Add words detours).
    Review marks Collect skipped — the guest left Collect without collecting.
    """
    in_review = controller.review_session() is not None
    if replace_current:
        app.pop_screen()
    if in_review:
        controller.mark_review_pull_skipped()
        controller.invalidate_push_preview()
        from .screens.review_update_screen import ReviewPushScreen

        app.push_screen(ReviewPushScreen(controller))
        return
    from .screens.preview_screen import PreviewScreen

    app.push_screen(PreviewScreen(controller, refresh_on_mount=True))


def continue_from_collect_preview(
    app: App[object],
    controller: TuiController,
    preview: PullPreview,
) -> bool:
    """Leave Collect without writing. Empty list → Add words; else Update preview.

    Returns True when Add words opened so the Collect screen can refresh on resume.
    """
    if preview.before_count == 0:
        from .screens.first_win_screen import AddWordsScreen

        app.push_screen(AddWordsScreen(controller))
        return True
    continue_to_update_apps(app, controller)
    return False
