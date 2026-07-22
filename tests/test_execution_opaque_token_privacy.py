"""Adversarial opaque tokens must not appear in sanitized output."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.privacy import (  # noqa: E402
    ADVERSARIAL_OPAQUE_TOKENS,
    sanitize_text,
    workspace_roots,
)

ADVERSARIAL = ADVERSARIAL_OPAQUE_TOKENS


def test_all_letter_base64_tokens_redacted(isolated_state_dir):
    del isolated_state_dir
    payload = " ".join(ADVERSARIAL)
    redacted = sanitize_text(payload, workspace_roots=workspace_roots(public_root=ROOT))
    for token in ADVERSARIAL:
        assert token not in redacted
    assert "[REDACTED]" in redacted


def test_opaque_tokens_absent_from_command_args(isolated_state_dir):
    del isolated_state_dir
    from scripts.execution_control.privacy import sanitize_command

    command = ["pytest", f"--token={ADVERSARIAL[0]}", ADVERSARIAL[1]]
    sanitized = sanitize_command(command, workspace_roots=workspace_roots(public_root=ROOT))
    joined = " ".join(sanitized)
    for token in ADVERSARIAL:
        assert token not in joined
