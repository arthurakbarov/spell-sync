"""wordlist.txt quality checks."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .config import WHITELIST_FILENAME
from .exit_codes import ExitCode
from .guest_messages import LINT_FIX_WRITE_FAILED, LINT_WHITELIST_UNREADABLE, WORD_LIST_UNREADABLE
from .io import detect_encoding, wordlist_unreadable, write_text_words
from .log import log
from .paths import project_root
from .project import ProjectContext
from .words import (
    WordSet,
    has_cyrillic,
    has_latin,
    is_hard_junk,
    merge_case_duplicates,
    normalize_token,
)

_whitelist_cache: WordSet | None = None
_whitelist_cache_path: Path | None = None

# --- Whitelist ---


def _project_lint_whitelist_path(wordlist_file: str | Path | None = None) -> Path:
    project_dir = (
        ProjectContext.build(wordlist_file).project_dir
        if wordlist_file is not None
        else project_root()
    )
    return project_dir / WHITELIST_FILENAME


def _read_whitelist_tokens(path: Path) -> WordSet | None:
    """None when the file exists but cannot be read as a text allow-list."""
    if not path.is_file():
        return set()
    try:
        encoding = detect_encoding(path) or "utf-8"
        text = path.read_text(encoding=encoding)
    except OSError, UnicodeError:
        return None
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        return None
    words: WordSet = set()
    for line in text.splitlines():
        token = normalize_token(line)
        if token and not token.startswith("#"):
            words.add(token)
    return words


def project_lint_whitelist_unreadable(wordlist_file: str | Path | None = None) -> bool:
    """True when a project allow-list exists but cannot be read as text."""
    path = _project_lint_whitelist_path(wordlist_file)
    if not path.is_file():
        return False
    return _read_whitelist_tokens(path) is None


def get_lint_whitelist(wordlist_file: str | Path | None = None) -> WordSet:
    global _whitelist_cache, _whitelist_cache_path
    from .bundled_files import bundled_path

    path = _project_lint_whitelist_path(wordlist_file)
    tokens = _read_whitelist_tokens(path) if path.is_file() else None
    if tokens is None:
        path = bundled_path(WHITELIST_FILENAME)
        if _whitelist_cache is not None and _whitelist_cache_path == path:
            return _whitelist_cache
        tokens = _read_whitelist_tokens(path) or set()
    elif _whitelist_cache is not None and _whitelist_cache_path == path:
        return _whitelist_cache
    _whitelist_cache = tokens
    _whitelist_cache_path = path
    return tokens


def load_wordlist_lines(path: str | Path) -> list[str] | None:
    """None — file unavailable, missing, or undecodable."""
    file_path = Path(path)
    if not file_path.is_file():
        return None
    if wordlist_unreadable(file_path):
        return None
    try:
        encoding = detect_encoding(file_path) or "utf-8"
        lines: list[str] = []
        with open(file_path, encoding=encoding, errors="strict") as handle:
            for raw in handle:
                if raw.strip().startswith("#"):
                    continue
                token = normalize_token(raw)
                if token:
                    lines.append(token)
        return lines
    except OSError, UnicodeError:
        return None


def load_wordlist_comment_header(path: str | Path) -> list[str]:
    """Leading comment/blank lines before the first word token."""
    file_path = Path(path)
    if not file_path.is_file():
        return []
    try:
        encoding = detect_encoding(file_path) or "utf-8"
        header: list[str] = []
        with open(file_path, encoding=encoding, errors="strict") as handle:
            for raw in handle:
                stripped = raw.strip()
                if stripped.startswith("#") or stripped == "":
                    header.append(raw.rstrip("\n"))
                    continue
                if normalize_token(raw):
                    break
                header.append(raw.rstrip("\n"))
        return header
    except OSError, UnicodeError:
        return []


def load_wordlist_all_comments(path: str | Path) -> list[str]:
    """All ``#`` comment lines in file order (header and mid-file)."""
    file_path = Path(path)
    if not file_path.is_file():
        return []
    try:
        encoding = detect_encoding(file_path) or "utf-8"
        with open(file_path, encoding=encoding, errors="strict") as handle:
            return [raw.rstrip("\n") for raw in handle if raw.strip().startswith("#")]
    except OSError, UnicodeError:
        return []


# --- Report ---


@dataclass
class LintReport:
    hard_junk: list[str] = field(default_factory=list)
    exact_dupes: list[str] = field(default_factory=list)
    unsorted: bool = False
    case_dupes: list[list[str]] = field(default_factory=list)
    homoglyphs: list[str] = field(default_factory=list)
    digit_only: list[str] = field(default_factory=list)
    edge_punct: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "hard_junk": self.hard_junk,
            "exact_dupes": self.exact_dupes,
            "unsorted": self.unsorted,
            "case_dupes": self.case_dupes,
            "homoglyphs": self.homoglyphs,
            "digit_only": self.digit_only,
            "edge_punct": self.edge_punct,
        }


def analyze_words(
    words: Iterable[str],
    *,
    wordlist_file: str | Path | None = None,
) -> LintReport:
    word_list = list(words)
    whitelist = get_lint_whitelist(wordlist_file)
    report = LintReport()

    report.hard_junk = sorted({w for w in word_list if is_hard_junk(w)})

    seen: WordSet = set()
    dupes: WordSet = set()
    for word in word_list:
        if word in seen:
            dupes.add(word)
        seen.add(word)
    report.exact_dupes = sorted(dupes)
    # Sort unique tokens before comparing so casefold ties are stable across hash seeds.
    unique_sorted = sorted(set(word_list), key=str.casefold)
    report.unsorted = word_list != unique_sorted

    by_casefold: dict[str, list[str]] = defaultdict(list)
    for word in unique_sorted:
        by_casefold[word.casefold()].append(word)
    report.case_dupes = sorted(
        [sorted(group) for group in by_casefold.values() if len(group) > 1],
        key=lambda group: group[0].casefold(),
    )
    report.case_dupes = [
        group for group in report.case_dupes if not all(item in whitelist for item in group)
    ]

    unique = set(word_list)
    report.homoglyphs = sorted(
        w for w in unique if has_cyrillic(w) and has_latin(w) and w not in whitelist
    )
    report.digit_only = sorted(w for w in unique if w.isdigit() and w not in whitelist)
    report.edge_punct = sorted(
        w
        for w in unique
        if w and w not in whitelist and (not w[0].isalnum() or not w[-1].isalnum())
    )
    return report


# --- Output ---


def _show_issue_list(items: list[str], title: str, *, sample: int = 12) -> int:
    if not items:
        return 0
    log.lint_group(title, len(items))
    for item in items[:sample]:
        log.lint_item(item)
    if len(items) > sample:
        log.lint_item(f"... and {len(items) - sample} more")
    return len(items)


def _show_case_dupes(groups: list[list[str]], *, sample: int = 12) -> int:
    if not groups:
        return 0
    log.lint_group("case duplicates", len(groups))
    for group in groups[:sample]:
        log.lint_item(" | ".join(group))
    if len(groups) > sample:
        log.lint_item(f"... and {len(groups) - sample} more")
    return len(groups)


def print_report(report: LintReport, *, sample: int = 12) -> tuple[int, int]:
    hard = 0
    hard += _show_issue_list(report.hard_junk, "hard junk (removable)", sample=sample)
    hard += _show_issue_list(report.exact_dupes, "exact duplicates (removable)", sample=sample)
    if report.unsorted:
        log.lint_note("[unsorted/not normalized]  -> fixable")
        hard += 1

    soft = 0
    soft += _show_issue_list(report.homoglyphs, "Cyrillic+Latin homoglyphs", sample=sample)
    soft += _show_case_dupes(report.case_dupes, sample=sample)
    soft += _show_issue_list(report.digit_only, "digits only", sample=sample)
    soft += _show_issue_list(report.edge_punct, "edge punctuation", sample=sample)
    return hard, soft


def _write_fixed_wordlist(
    path: Path,
    cleaned: list[str],
    header: list[str],
    *,
    trailing_comments: list[str] | None = None,
) -> bool:
    parts: list[str] = []
    if header:
        parts.append("\n".join(header))
    body = "\n".join(cleaned)
    if cleaned:
        body += "\n"
    if body:
        parts.append(body.rstrip("\n"))
    if trailing_comments:
        parts.append("\n".join(trailing_comments))
    text = "\n".join(parts)
    if text and not text.endswith("\n"):
        text += "\n"
    if not header and not trailing_comments:
        return write_text_words(path, cleaned, "utf-8", bom=False)
    try:
        from .io import atomic_write

        atomic_write(path, text.encode("utf-8"))
    except OSError:
        return False
    return True


# --- CLI ---


def run_lint(
    wordlist_file: str | Path,
    *,
    fix: bool = False,
    strict: bool = False,
    own_outcome: bool = True,
) -> ExitCode:
    """Lint the word list.

    When ``own_outcome`` is False (CLI presenter path), skip terminal
    ``[ABORT]`` / ``[summary]`` lines so the caller can emit one unified outcome.
    Progress details and issue lists still print.
    """
    path = Path(wordlist_file)
    raw_lines = load_wordlist_lines(path)
    if raw_lines is None:
        if own_outcome:
            log.abort(WORD_LIST_UNREADABLE)
        else:
            log.detail(WORD_LIST_UNREADABLE)
        return ExitCode.WORDLIST_UNREADABLE
    if project_lint_whitelist_unreadable(path):
        if own_outcome:
            log.abort(LINT_WHITELIST_UNREADABLE)
        else:
            log.detail(LINT_WHITELIST_UNREADABLE)
        return ExitCode.LINT_FAILED

    log.detail(f"{len(raw_lines)} lines")
    report = analyze_words(raw_lines, wordlist_file=path)

    if fix:
        # Re-verify the file is still readable before rewriting comments.
        if load_wordlist_lines(path) is None:
            if own_outcome:
                log.abort(WORD_LIST_UNREADABLE)
            else:
                log.detail(WORD_LIST_UNREADABLE)
            return ExitCode.WORDLIST_UNREADABLE
        header = list(load_wordlist_comment_header(path))
        header_comment_set = {line for line in header if line.strip().startswith("#")}
        trailing_comments = [
            comment
            for comment in load_wordlist_all_comments(path)
            if comment not in header_comment_set
        ]
        cleaned = merge_case_duplicates(raw_lines)
        if not _write_fixed_wordlist(
            path,
            cleaned,
            header,
            trailing_comments=trailing_comments,
        ):
            if own_outcome:
                log.abort(LINT_FIX_WRITE_FAILED)
            else:
                log.detail(LINT_FIX_WRITE_FAILED)
            return ExitCode.PUSH_ABORT
        log.fix(f"{len(raw_lines)} -> {len(cleaned)} (soft warnings left unchanged)")
        raw_lines = cleaned
        report = analyze_words(raw_lines, wordlist_file=path)

    hard, soft = print_report(report)
    if own_outcome:
        log.summary(hard, soft)
    else:
        log.detail(f"hard={hard} soft={soft}")
    if hard > 0 and not fix:
        log.detail("run `spell-sync lint --fix` to auto-fix hard issues")
    if hard > 0 or (strict and soft > 0):
        return ExitCode.LINT_FAILED
    return ExitCode.OK
