"""Path redaction for support and session exports."""

import os
import re
from pathlib import Path, PureWindowsPath


def home_directory() -> Path:
    return Path.home().resolve()


def _windows_drive_external_name(raw: str) -> str | None:
    windows = PureWindowsPath(raw)
    if windows.drive:
        return f"<external>/{windows.name or 'path'}"
    return None


def redact_path(path: str | Path | None, *, home: Path | None = None) -> str | None:
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return raw
    home_path = (home or home_directory()).resolve()
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
    except OSError:
        return "<external>/path"
    try:
        relative = candidate.relative_to(home_path)
        return "~/" + relative.as_posix()
    except ValueError:
        pass
    if "\\" in raw or re.match(r"[A-Za-z]:", raw):
        windows = PureWindowsPath(raw)
        return f"<external>/{windows.name or 'path'}"
    if os.name == "nt":  # pragma: no cover -- Windows hosts only
        external = _windows_drive_external_name(raw)
        if external is not None:
            return external
    name = candidate.name or "path"
    return f"<external>/{name}"


def redact_profile_label(identifier: str, index: int) -> str:
    safe = identifier.replace("_", "-")
    return f"{safe}-profile-{index + 1}"
