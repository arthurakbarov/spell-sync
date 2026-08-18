"""User onboarding copy is present in product concepts."""

from spell_sync.application import product_concepts as pc


def test_collect_and_update_labels() -> None:
    assert "Collect" in pc.COLLECT_WORDS_TECHNICAL
    assert "Update" in pc.UPDATE_APPS_TECHNICAL
    assert "Pull" in pc.COLLECT_WORDS_TECHNICAL
    assert "Push" in pc.UPDATE_APPS_TECHNICAL


def test_safety_copy() -> None:
    assert "Nothing will be removed" in pc.PULL_PREVIEW_SAFETY
    assert "may be removed" in pc.PUSH_PREVIEW_SAFETY.lower()
    assert "never" in pc.BUILTIN_DICTIONARY_GUARANTEE.lower()


def test_problem_statement() -> None:
    assert "misspelled" in pc.USER_PROBLEM_STATEMENT.lower()
    assert "personal word" in pc.USER_PROBLEM_STATEMENT.lower()


def test_beginner_welcome_and_primary_path() -> None:
    assert pc.SETUP_START_BUTTON_LABEL == "Start here"
    assert "Review and update" in pc.REVIEW_AND_UPDATE_LABEL
    assert "personal word" in pc.WELCOME_WHAT_YOU_DO.lower()
    assert "spell-sync add" in pc.CLI_ADD_HELP.lower() or "Add words" in pc.CLI_ADD_HELP
    from spell_sync.guest_messages import ADD_NEXT_HINT, EMPTY_WORDLIST_DOCTOR, INIT_NEXT_HINT

    assert "spell-sync add" in EMPTY_WORDLIST_DOCTOR
    assert "spell-sync add" in INIT_NEXT_HINT
    assert "spell-sync plan" in ADD_NEXT_HINT
    assert "Update my apps" in ADD_NEXT_HINT
    assert "confirm" in pc.REVIEW_START_BODY.lower()
    assert "Usual path after setup:\n1." in pc.REVIEW_START_BODY
    assert "Usual path after setup:\n\n" not in pc.REVIEW_START_BODY
    assert "Add words" in pc.REVIEW_START_BODY or "add" in pc.REVIEW_START_BODY.lower()
    assert "confirm" in pc.REVIEW_AND_UPDATE_HELP.lower()
    assert "Nothing is removed" in pc.COLLECT_WORDS_HELP
    assert "built-in" in pc.UPDATE_APPS_HELP.lower()
    assert "ready" in pc.CHECK_APPS_HELP.lower()
    # Field label lives next to the picker — not as a trailing empty line in the intro.
    assert not pc.CHANGE_WORDLIST_BODY.rstrip().endswith("Path to wordlist.txt:")
    # Empty collect: only forward path is Update — not optional "you can skip".
    assert "You can skip" not in pc.PULL_PREVIEW_EMPTY_NEXT
    assert pc.PULL_PREVIEW_EMPTY_NEXT.startswith("Next:")
    # Empty Update: only forward path is review summary — not "Finish without...".
    assert "You can skip" not in pc.PUSH_PREVIEW_EMPTY_NEXT
    assert pc.PUSH_PREVIEW_EMPTY_NEXT.startswith("Next:")
    assert "Continue" in pc.CONTINUE_TO_REVIEW_SUMMARY_LABEL
    assert "without" in pc.FINISH_WITHOUT_UPDATE_LABEL.lower()
    assert "Custom dictionaries were updated" in pc.REVIEW_SESSION_DONE_MATCHED
    assert "restart" in pc.REVIEW_SESSION_DONE_MATCHED.lower()
    assert "apps match your word list" not in pc.REVIEW_SESSION_DONE_MATCHED.lower()
    assert "spell-sync-words.txt" not in pc.REVIEW_SESSION_DONE_MATCHED
    assert "spell-sync-words.txt" in pc.review_session_done_matched(editors_updated=True)
    assert "spell-sync-words.txt" in pc.EDITOR_WIRE_HINT
    assert pc.ADD_WORDS_LABEL.startswith("Add words")
    assert "Setup is done" in pc.FIRST_WIN_INTRO
    assert "where you want words to work" in pc.SETUP_APPS_GOAL_LINE.lower()
    assert "Collect later" in pc.SETUP_APPS_GOAL_LINE
    assert "empty" in pc.DASHBOARD_EMPTY_WORDLIST_CTA.lower()
    assert "Add words" in pc.PULL_PREVIEW_EMPTY_LIST_EMPTY_NEXT
