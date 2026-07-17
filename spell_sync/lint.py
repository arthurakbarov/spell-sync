"""wordlist.txt quality checks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Union

from .config import SHORT_WARN_LEN, WHITELIST_FILENAME
from .exit_codes import ExitCode
from .io import detect_encoding, write_text_words
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


def get_lint_whitelist(wordlist_file: Union[str, Path, None] = None) -> WordSet:
    global _whitelist_cache, _whitelist_cache_path
    project_dir = (
        ProjectContext.build(wordlist_file).project_dir
        if wordlist_file is not None
        else project_root()
    )
    path = project_dir / WHITELIST_FILENAME
    if not path.is_file():
        from .bundled_files import bundled_path

        path = bundled_path(WHITELIST_FILENAME)
    if _whitelist_cache is not None and _whitelist_cache_path == path:
        return _whitelist_cache
    words: WordSet = set()
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            token = normalize_token(line)
            if token and not token.startswith("#"):
                words.add(token)
    _whitelist_cache = words
    _whitelist_cache_path = path
    return words


def load_wordlist_lines(path: Union[str, Path]) -> list[str] | None:
    """None — file unavailable or missing."""
    file_path = Path(path)
    if not file_path.is_file():
        return None
    try:
        encoding = detect_encoding(file_path) or "utf-8"
        lines: list[str] = []
        with open(file_path, "r", encoding=encoding) as handle:
            for raw in handle:
                if raw.strip().startswith("#"):
                    continue
                token = normalize_token(raw)
                if token:
                    lines.append(token)
        return lines
    except OSError:
        return None


# --- Report ---


@dataclass
class LintReport:
    hard_junk: List[str] = field(default_factory=list)
    exact_dupes: List[str] = field(default_factory=list)
    unsorted: bool = False
    case_dupes: List[List[str]] = field(default_factory=list)
    homoglyphs: List[str] = field(default_factory=list)
    very_short: List[str] = field(default_factory=list)
    digit_only: List[str] = field(default_factory=list)
    edge_punct: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "hard_junk": self.hard_junk,
            "exact_dupes": self.exact_dupes,
            "unsorted": self.unsorted,
            "case_dupes": self.case_dupes,
            "homoglyphs": self.homoglyphs,
            "very_short": self.very_short,
            "digit_only": self.digit_only,
            "edge_punct": self.edge_punct,
        }


def analyze_words(
    words: Iterable[str],
    *,
    wordlist_file: Union[str, Path, None] = None,
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
    report.unsorted = word_list != sorted(set(word_list), key=str.casefold)

    by_casefold: Dict[str, List[str]] = defaultdict(list)
    for word in set(word_list):
        by_casefold[word.casefold()].append(word)
    report.case_dupes = sorted(
        group
        for group in by_casefold.values()
        if len(group) > 1 and not all(item in whitelist for item in group)
    )

    unique = set(word_list)
    report.homoglyphs = sorted(
        w for w in unique if has_cyrillic(w) and has_latin(w) and w not in whitelist
    )
    report.very_short = sorted(w for w in unique if len(w) <= SHORT_WARN_LEN and w not in whitelist)
    report.digit_only = sorted(w for w in unique if w.isdigit() and w not in whitelist)
    report.edge_punct = sorted(
        w
        for w in unique
        if w and w not in whitelist and (not w[0].isalnum() or not w[-1].isalnum())
    )
    return report


# --- Output ---


def _show_issue_list(items: List[str], title: str, *, sample: int = 12) -> int:
    if not items:
        return 0
    log.lint_group(title, len(items))
    for item in items[:sample]:
        log.lint_item(item)
    if len(items) > sample:
        log.lint_item(f"… and {len(items) - sample} more")
    return len(items)


def _show_case_dupes(groups: List[List[str]], *, sample: int = 12) -> int:
    if not groups:
        return 0
    log.lint_group("case duplicates", len(groups))
    for group in groups[:sample]:
        log.lint_item(" | ".join(group))
    if len(groups) > sample:
        log.lint_item(f"… and {len(groups) - sample} more")
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
    soft += _show_issue_list(report.very_short, f"very short (<= {SHORT_WARN_LEN})", sample=sample)
    soft += _show_issue_list(report.digit_only, "digits only", sample=sample)
    soft += _show_issue_list(report.edge_punct, "edge punctuation", sample=sample)
    return hard, soft


# --- CLI ---


def run_lint(
    wordlist_file: Union[str, Path],
    *,
    fix: bool = False,
    strict: bool = False,
) -> ExitCode:
    raw_lines = load_wordlist_lines(wordlist_file)
    if raw_lines is None:
        log.abort(f"wordlist unavailable: {wordlist_file}")
        return ExitCode.WORDLIST_UNREADABLE

    log.section(f"lint: {len(raw_lines)} lines")
    report = analyze_words(raw_lines, wordlist_file=wordlist_file)

    if fix:
        cleaned = merge_case_duplicates(raw_lines)
        if not write_text_words(wordlist_file, cleaned, "utf-8", bom=False):
            log.abort("lint --fix: failed to write wordlist.")
            return ExitCode.PUSH_ABORT
        log.fix(f"{len(raw_lines)} -> {len(cleaned)} (soft warnings left unchanged)")
        return ExitCode.OK

    hard, soft = print_report(report)
    log.summary(hard, soft)
    if hard > 0:
        log.detail("run `spell-sync lint --fix` to auto-fix hard issues")
    if hard > 0 or (strict and soft > 0):
        return ExitCode.LINT_FAILED
    return ExitCode.OK
