"""Unified transparent terminal output for operations."""

from __future__ import annotations


class Log:
    """Structured messages: [read], [write], [info], [WARN], [done]."""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet

    # --- General ---

    def section(self, title: str) -> None:
        self._loud(f"=== {title} ===")

    def info(self, message: str) -> None:
        self._loud(f"[info ] {message}")

    def warn(self, message: str) -> None:
        self._loud(f"[WARN] {message}")

    def error(self, message: str) -> None:
        self._loud(f"[ERROR] {message}")

    def done(self, message: str) -> None:
        self._loud(f"[done ] {message}")

    def abort(self, message: str) -> None:
        self._loud(f"[ABORT] {message}")

    def fix(self, message: str) -> None:
        self._loud(f"[fix ] {message}")

    def summary(self, hard: int, soft: int) -> None:
        self._loud(f"[summary] hard={hard} soft={soft}")

    def detail(self, message: str) -> None:
        """Explanation without prefix (indented)."""
        if self.quiet:
            return
        print(f"       {message}")

    # --- Dictionaries (read / write / status) ---

    def dictionary_read(self, count: int, fmt: str, path: str) -> None:
        self._loud(f"[read ] {count:>5}  ({fmt})  {path}")

    def dictionary_write(self, count: int, fmt: str, path: str) -> None:
        self._loud(f"[write] {count:>5}  ({fmt})  {path}")

    def dictionary_status(
        self,
        name: str,
        target_count: int,
        local_count: int,
        add_count: int,
        remove_count: int,
    ) -> None:
        if self.quiet:
            return
        self._emit(
            f"  {name}: wordlist(target)={target_count} local={local_count} "
            f"push +{add_count} / -{remove_count}"
        )

    def dictionary_word_diff(
        self,
        label: str,
        words: tuple[str, ...],
        *,
        sample: int = 12,
    ) -> None:
        """Word list for status --verbose."""
        if self.quiet or not words:
            return
        shown = ", ".join(words[:sample])
        if len(words) > sample:
            shown += f", … (+{len(words) - sample})"
        print(f"      {label}: {shown}")

    # --- Lint ---

    def lint_group(self, title: str, count: int) -> None:
        if self.quiet:
            return
        print(f"  [{title}] {count}")

    def lint_item(self, text: str) -> None:
        if self.quiet:
            return
        print(f"      {text}")

    def lint_note(self, text: str) -> None:
        if self.quiet:
            return
        print(f"  {text}")

    # --- Internal ---

    def _loud(self, message: str) -> None:
        if not self.quiet:
            self._emit(message)

    def _emit(self, message: str) -> None:
        print(message)


log = Log()
