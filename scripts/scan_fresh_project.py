#!/usr/bin/env python3
"""Fail closed on historicity / retired-compat residue in the product tree.

Scans git-tracked and untracked non-ignored text files under the package root.
Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Product-tree bans (historicity / compat museums). Runtime words like operation
# "stage" are fine. "compatible" as in Chrome-compatible dictionary format is fine.
# Patterns avoid embedding banned literals in this file's own source lines.
_LEG = "lega" + "cy"
_DEP = "deprecat" + "ed"
_FORMER = "former" + "ly"
_MIG = "migrated" + " from"
FORBIDDEN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("hist-legacy", re.compile(rf"(?i)\b{_LEG}\b")),
    ("hist-deprecated", re.compile(rf"(?i)\b{_DEP}\b")),
    ("hist-bw-compat", re.compile(r"(?i)back" + r"ward[\s-]?compat")),
    ("hist-compat-shim", re.compile(r"(?i)compat(?:ibility)?\s+shim")),
    ("hist-call-site", re.compile(r"(?i)call-site\s+compatibility")),
    ("hist-kept-older", re.compile(r"(?i)kept\s+for\s+(?:older|compat)")),
    ("hist-former", re.compile(rf"(?i)\b{_FORMER}\b")),
    ("hist-migrated", re.compile(rf"(?i){_MIG}")),
    ("hist-phase", re.compile(r"(?i)\bphase[\s_-]*\d+\b")),
    ("hist-wave", re.compile(r"(?i)\bwave\s+[a-z0-9]+\b")),
)

ALLOW_LINE = re.compile(
    r"(?i)(?:forbid|ban|reject|must not|do not|scan_fresh|FORBIDDEN|"
    r"obsolete marker|target-capabilities|_LEG|_DEP)"
)

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".zip",
    ".whl",
    ".pyc",
    ".so",
    ".dylib",
    ".woff",
    ".woff2",
    ".ttf",
}
MAX_FILE_BYTES = 1_500_000


@dataclass(frozen=True, slots=True)
class Hit:
    path: str
    line_no: int
    category: str
    preview: str


def _scan_files(root: Path) -> list[Path]:
    out = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for raw in out.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace")
        path = root / rel
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if not path.is_file():
            continue
        paths.append(path)
    return paths


def scan(root: Path) -> list[Hit]:
    hits: list[Hit] = []
    for path in _scan_files(root):
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            if ALLOW_LINE.search(line):
                continue
            for category, pattern in FORBIDDEN:
                if pattern.search(line):
                    hits.append(
                        Hit(
                            path=rel,
                            line_no=line_no,
                            category=category,
                            preview=line.strip()[:160],
                        )
                    )
                    break
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Package root to scan (default: this package tree)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    hits = scan(root)
    if hits:
        print("FRESH_PROJECT_SCAN_RESULT=failed")
        print(f"FRESH_PROJECT_SCAN_HITS={len(hits)}")
        for hit in hits[:80]:
            print(f"{hit.path}:{hit.line_no}: [{hit.category}] {hit.preview}")
        if len(hits) > 80:
            print(f"…and {len(hits) - 80} more")
        return 1
    print("FRESH_PROJECT_SCAN_RESULT=success")
    print("FRESH_PROJECT_SCAN_HITS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
