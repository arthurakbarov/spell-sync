#!/usr/bin/env python3
"""Lean privacy scan of git-tracked content (secrets + maintainer home paths).

Stdlib only. Does not replace structural checks in check_agent_config.py.
Intended for edit-loop optional use and hard-fail on publish preflight.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY")),
    ("github-pat", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("github-fine-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)

MAINTAINER_USER = "arthur" + "akbarov"
MAINTAINER_PATH = re.compile(rf"(?:/Users|/home)/{re.escape(MAINTAINER_USER)}\b")

# Lines that document scanners or clearly mark fixtures/examples.
ALLOW_LINE = re.compile(
    r"(?i)(?:example|placeholder|redacted|YOUR_|xxxx|dummy|fake.?token|"
    r"token-shaped|secret-token(?:-like|-value)?|"
    r"rg\s+-i|BEGIN \(RSA\|OPENSSH\|EC\)|"
    r"ghp_\{|github_pat_\{|sk-ant-\[|xox\[baprs\])"
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
class PrivacyHit:
    path: str
    line_no: int
    category: str
    preview: str


def _tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
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
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        paths.append(path)
    return paths


def _redact_preview(text: str) -> str:
    preview = text.strip()

    def _shorten(match: re.Match[str]) -> str:
        return match.group(1) + "..."

    preview = re.sub(r"(ghp_[A-Za-z0-9]{4})[A-Za-z0-9]+", _shorten, preview)
    preview = re.sub(r"(github_pat_[A-Za-z0-9_]{4})[A-Za-z0-9_]+", _shorten, preview)
    preview = re.sub(r"(sk-ant-[A-Za-z0-9-]{4})[A-Za-z0-9-]+", _shorten, preview)
    preview = re.sub(r"(xox[baprs]-[A-Za-z0-9-]{4})[A-Za-z0-9-]+", _shorten, preview)
    preview = re.sub(
        r"BEGIN [A-Z0-9 ]*PRIVATE KEY",
        "BEGIN ... PRIVATE KEY",
        preview,
    )
    if len(preview) > 100:
        preview = preview[:100] + "..."
    return preview


def scan_privacy_tree(root: Path | None = None) -> list[PrivacyHit]:
    base = root or ROOT
    hits: list[PrivacyHit] = []
    for path in _tracked_files(base):
        rel = path.relative_to(base).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if ALLOW_LINE.search(line):
                continue
            for category, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    hits.append(PrivacyHit(rel, line_no, category, _redact_preview(line)))
            if MAINTAINER_PATH.search(line):
                hits.append(
                    PrivacyHit(
                        rel,
                        line_no,
                        "maintainer-home-path",
                        _redact_preview(line),
                    )
                )
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root (default: spell-sync checkout)",
    )
    args = parser.parse_args(argv)
    hits = scan_privacy_tree(args.root.resolve())
    if hits:
        print("PRIVACY_SCAN_RESULT=failed")
        print(f"PRIVACY_SCAN_HITS={len(hits)}")
        for hit in hits[:50]:
            print(f"PRIVACY_SCAN_HIT={hit.path}:{hit.line_no}:{hit.category}:{hit.preview}")
        if len(hits) > 50:
            print(f"PRIVACY_SCAN_HIT_OMITTED={len(hits) - 50}")
        return 1
    print("PRIVACY_SCAN_RESULT=success")
    print("PRIVACY_SCAN_HITS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
