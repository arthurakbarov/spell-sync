"""Guest Status screen summary copy."""

from .field_blocks import format_aligned_fields
from .product_concepts import WORD_LIST_UNREADABLE_STATUS
from .reports import StatusDetailSnapshot


def format_status_summary(snapshot: StatusDetailSnapshot) -> str:
    """Align ``Label: value`` paths/counts for the Status summary block."""
    rows: list[tuple[str, object]] = [
        ("Word list", snapshot.wordlist_path),
        ("Project", snapshot.project_dir),
    ]
    if snapshot.config_path:
        rows.append(("Config", snapshot.config_path))

    lines: list[str] = ["Status"]
    if snapshot.load_error:
        lines.extend(format_aligned_fields(rows))
        lines.append(f"× {snapshot.load_error}")
    elif snapshot.wordlist_error is not None:
        lines.extend(format_aligned_fields(rows))
        lines.append(f"× {WORD_LIST_UNREADABLE_STATUS}")
    else:
        rows.append(("Words in your list", snapshot.wordlist_count))
        lines.extend(format_aligned_fields(rows))
        if snapshot.destructive_risk:
            lines.append(f"! {snapshot.destructive_risk}")
        lines.extend(f"! {warning}" for warning in snapshot.warnings)
        if not snapshot.targets:
            lines.append("· No applications configured")

    skip_rows: list[tuple[str, object]] = []
    if snapshot.skipped_unreadable:
        skip_rows.append(("Skipped unreadable", ", ".join(snapshot.skipped_unreadable)))
    if snapshot.skipped_corrupt:
        skip_rows.append(("Skipped corrupt", ", ".join(snapshot.skipped_corrupt)))
    if skip_rows:
        lines.extend(["", *format_aligned_fields(skip_rows)])
    return "\n".join(lines)
