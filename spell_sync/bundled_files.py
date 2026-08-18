"""Example files shipped inside the installed package."""

from pathlib import Path

_BUNDLED_DIR = Path(__file__).resolve().parent / "bundled"


def bundled_path(name: str) -> Path:
    return _BUNDLED_DIR / name
