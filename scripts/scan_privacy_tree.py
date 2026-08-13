#!/usr/bin/env python3
"""Scan the repository tree for secrets and absolute personal home paths.

Checks git-tracked and untracked non-ignored files. Stdlib only.
"""

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
    # Generic sk- tokens (vendor API keys and similar).
    ("api-key-sk", re.compile(r"\bsk-[A-Za-z0-9-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)

# Package author login (also in pyproject authors); must not appear as a home path.
AUTHOR_LOGIN = "arthurakbarov"
AUTHOR_HOME_PATH = re.compile(rf"(?:/Users|/home)/{re.escape(AUTHOR_LOGIN)}\b")

# Lines that document scanners or clearly mark fixtures/examples.
ALLOW_LINE = re.compile(
    r"(?i)(?:example|placeholder|redacted|YOUR_|xxxx|dummy|fake.?token|"
    r"token-shaped|secret-token(?:-like|-value)?|"
    r"rg\s+-i|BEGIN \(RSA\|OPENSSH\|EC\)|"
    r"ghp_\{|github_pat_\{|sk-\[|xox\[baprs\])"
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


def _scan_files(root: Path) -> list[Path]:
    """Tracked + untracked (non-ignored) text-like files under ``root``."""
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


def _redact_preview(text: str) -> str:
    preview = text.strip()

    def _shorten(match: re.Match[str]) -> str:
        return match.group(1) + "..."

    preview = re.sub(r"(ghp_[A-Za-z0-9]{4})[A-Za-z0-9]+", _shorten, preview)
    preview = re.sub(r"(github_pat_[A-Za-z0-9_]{4})[A-Za-z0-9_]+", _shorten, preview)
    preview = re.sub(r"(sk-[A-Za-z0-9-]{4})[A-Za-z0-9-]+", _shorten, preview)
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
    for path in _scan_files(base):
        rel = path.relative_to(base).as_posix()
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            hits.append(
                PrivacyHit(
                    rel,
                    0,
                    "file-too-large",
                    f"skipped-scan size={size} max={MAX_FILE_BYTES}",
                )
            )
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for category, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    hits.append(PrivacyHit(rel, line_no, category, _redact_preview(line)))
            if AUTHOR_HOME_PATH.search(line) and not ALLOW_LINE.search(line):
                hits.append(
                    PrivacyHit(
                        rel,
                        line_no,
                        "personal-home-path",
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
        help="Repository root (default: this checkout)",
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
