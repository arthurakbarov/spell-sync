"""Format ``Label: value`` field blocks for guest-facing output.

``:`` is glued to the label; pad after ``:`` so values share one column within a
contiguous multi-line block. One-field blocks use a single space after ``:``.
"""

import re
from collections.abc import Iterable, Sequence

# Sentence-case labels in product copy.
_FIELD_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /-]{0,48}):(\s*)(.*)$")


def format_aligned_fields(rows: Sequence[tuple[str, object]]) -> list[str]:
    """Format key/value pairs as one aligned field block."""
    if not rows:
        return []
    width = max(len(label) for label, _ in rows) + 1
    return [f"{label + ':':<{width}} {value}" for label, value in rows]


def format_indented_fields(
    rows: Sequence[tuple[str, object]],
    *,
    indent: str = "  ",
) -> list[str]:
    """Aligned field block with a shared left indent (details panels)."""
    return [f"{indent}{line}" for line in format_aligned_fields(rows)]


def iter_field_blocks(text: str) -> Iterable[list[tuple[str, str, str, int]]]:
    """Yield contiguous field-line runs.

    Each item is ``(key, spaces_after_colon, value, value_column)``.
    Leading indent is stripped before matching; ``value_column`` is measured on
    the stripped line (alignment within the block, not absolute screen column).
    """
    block: list[tuple[str, str, str, int]] = []
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith(("!", "×", "✓", "·", "#")):
            if block:
                yield block
                block = []
            continue
        match = _FIELD_LINE_RE.match(stripped)
        if not match:
            if block:
                yield block
                block = []
            continue
        key, spaces, value = match.group(1), match.group(2), match.group(3)
        value_col = len(key) + 1 + len(spaces)
        block.append((key, spaces, value, value_col))
    if block:
        yield block


def field_block_alignment_errors(text: str) -> list[str]:
    """Return human-readable alignment violations (empty means ok)."""
    errors: list[str] = []
    for block in iter_field_blocks(text):
        if len(block) == 1:
            key, spaces, _value, _col = block[0]
            if spaces != " ":
                errors.append(
                    f"single-field '{key}:' must use exactly one space after ':' "
                    f"(got {len(spaces)} spaces)"
                )
            continue
        columns = {item[3] for item in block}
        if len(columns) != 1:
            keys = ", ".join(item[0] for item in block)
            cols = ", ".join(str(item[3]) for item in block)
            errors.append(
                f"multi-field block values misaligned (keys: {keys}; value columns: {cols})"
            )
            continue
        for key, spaces, _value, _col in block:
            if len(spaces) < 1:
                errors.append(f"field '{key}:' missing space before value")
    return errors


def assert_guest_field_blocks_aligned(text: str) -> None:
    errors = field_block_alignment_errors(text)
    if errors:
        preview = "\n".join(text.splitlines()[:24])
        raise AssertionError(
            "guest field-block contract violated:\n- "
            + "\n- ".join(errors)
            + f"\n\ntext:\n{preview}"
        )
