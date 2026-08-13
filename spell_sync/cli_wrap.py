"""Soft-wrap human CLI lines to a fixed column width."""

from .config import CLI_OUTPUT_WIDTH, CLI_WRAP_CONTINUATION_INDENT


def wrap_cli_line(
    message: str,
    *,
    width: int = CLI_OUTPUT_WIDTH,
    continuation_indent: int = CLI_WRAP_CONTINUATION_INDENT,
) -> list[str]:
    """Wrap ``message`` so every physical line is at most ``width`` characters.

    Leading spaces on the primary line are preserved. Continuation lines use that
    same base indent plus ``continuation_indent`` extra spaces. Breaks prefer
    whitespace so words stay intact when possible; a single token longer than the
    available width is hard-split.
    """
    if width < 1:
        width = 1
    if "\n" in message:
        lines: list[str] = []
        for part in message.splitlines():
            lines.extend(wrap_cli_line(part, width=width, continuation_indent=continuation_indent))
        if message.endswith("\n"):
            lines.append("")
        return lines or [""]
    if len(message) <= width:
        return [message]

    leading = len(message) - len(message.lstrip(" "))
    body = message[leading:]
    base = " " * leading
    hang = max(0, continuation_indent)
    cont = " " * (leading + hang)
    while len(cont) >= width and hang > 0:
        hang -= 1
        cont = " " * (leading + hang)
    if len(cont) >= width:
        cont = ""

    lines = []
    remaining = body
    prefix = base
    while remaining:
        avail = width - len(prefix)
        if avail < 1:
            # Degenerate indent — emit without prefix so progress continues.
            prefix = ""
            avail = width
        if len(remaining) <= avail:
            lines.append(prefix + remaining)
            break
        chunk = remaining[:avail]
        brk = chunk.rfind(" ")
        if brk <= 0:
            piece = remaining[:avail]
            remaining = remaining[avail:]
        else:
            piece = remaining[:brk]
            remaining = remaining[brk + 1 :].lstrip(" ")
        lines.append(prefix + piece)
        prefix = cont
    return lines
