"""Load spell-sync.toml with identical semantics on all supported Python versions."""

from __future__ import annotations

import tomllib
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

_CONFIG_FILENAME = "spell-sync.toml"
_CONFIG_DIR_NAME = "spell-sync"

KNOWN_KEYS: dict[str, frozenset[str]] = {
    "dictionaries": frozenset(
        {
            "editors",
            "chrome",
            "edge",
            "brave",
            "vivaldi",
            "firefox",
            "neovim",
            "jetbrains",
            "hunspell",
            "obsidian",
            "libreoffice",
        }
    ),
    "neovim": frozenset({"mkspell_after_push"}),
    "push": frozenset(
        {
            "guard_wordlist_max",
            "guard_local_min",
            "strict",
            "max_removals_without_confirm",
        }
    ),
    "io": frozenset({"backup_keep"}),
}


class ConfigStatus(str, Enum):
    ABSENT = "absent"
    VALID = "valid"
    SYNTAX_ERROR = "syntax_error"
    UNKNOWN_KEY = "unknown_key"
    INVALID_TYPE = "invalid_type"
    UNSUPPORTED_SCHEMA = "unsupported_schema"


@dataclass(frozen=True)
class ConfigDiagnostic:
    path: str
    message: str
    kind: ConfigStatus


@dataclass(frozen=True)
class ConfigLoadResult:
    status: ConfigStatus
    config: Dict[str, Dict[str, Any]] | None
    diagnostics: tuple[ConfigDiagnostic, ...]


def _parse_toml_with_issues(path: Path) -> Tuple[Dict[str, Dict[str, Any]], list[str]]:
    """Parse one TOML file with standard-library tomllib."""
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(f"{path}: {exc}")
        return {}, issues
    try:
        # Always pass str: tomllib.loads rejects bytes (TypeError on 3.11+).
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        issues.append(f"{path}: {exc}")
        return {}, issues
    except TypeError as exc:  # pragma: no cover -- defensive
        issues.append(f"{path}: {exc}")
        return {}, issues

    data: Dict[str, Dict[str, Any]] = {}
    for section, values in parsed.items():
        if not isinstance(values, dict):
            issues.append(f"{path}: [{section}] must be a table")
            continue
        section_data: Dict[str, Any] = {}
        for key, value in values.items():
            if isinstance(value, bool):
                section_data[key] = value
            elif isinstance(value, int) and not isinstance(value, bool):
                section_data[key] = value
            else:
                issues.append(f"{path}: [{section}] {key}: unsupported value type")
        if section_data:
            data[section] = section_data
    return data, issues


def _parse_toml(path: Path) -> Dict[str, Dict[str, Any]]:
    data, _issues = _parse_toml_with_issues(path)
    return data


def config_paths_for_wordlist(wordlist: Path) -> list[Path]:
    """User config first; project config adjacent to the effective wordlist."""
    home_config = Path.home() / ".config" / _CONFIG_DIR_NAME / _CONFIG_FILENAME
    project_config = wordlist.resolve().parent / _CONFIG_FILENAME
    return [home_config, project_config]


def config_paths(*, wordlist: Path | None = None) -> list[Path]:
    if wordlist is not None:
        return config_paths_for_wordlist(wordlist)
    from .paths import project_root

    home_config = Path.home() / ".config" / _CONFIG_DIR_NAME / _CONFIG_FILENAME
    project_config = project_root() / _CONFIG_FILENAME
    return [home_config, project_config]


_settings_cache: ConfigLoadResult | None = None
_settings_cache_key: tuple[str, ...] | None = None
_active_settings: ContextVar[Dict[str, Dict[str, Any]] | None] = ContextVar(
    "_active_settings",
    default=None,
)


def clear_settings_cache() -> None:
    """Drop cached settings (tests and long-lived processes)."""
    global _settings_cache, _settings_cache_key
    _settings_cache = None
    _settings_cache_key = None
    _active_settings.set(None)


def bind_active_settings(config: Dict[str, Dict[str, Any]]) -> None:
    """Use runtime config for dictionary flags and hook settings in this process."""
    _active_settings.set(config)


def _load_config_uncached(*, wordlist: Path | None = None) -> ConfigLoadResult:
    merged: Dict[str, Dict[str, Any]] = {}
    diagnostics: list[ConfigDiagnostic] = []
    found_file = False
    for path in config_paths(wordlist=wordlist):
        if not path.is_file():
            continue
        found_file = True
        data, file_issues = _parse_toml_with_issues(path)
        for issue in file_issues:
            if "unsupported value type" in issue or "must be a table" in issue:
                kind = ConfigStatus.INVALID_TYPE
            else:
                kind = ConfigStatus.SYNTAX_ERROR
            diagnostics.append(ConfigDiagnostic(str(path), issue, kind))
        if file_issues and not data:
            # Hard syntax error — fail closed for this file
            return ConfigLoadResult(
                ConfigStatus.SYNTAX_ERROR,
                None,
                tuple(diagnostics),
            )
        for section, values in data.items():
            merged.setdefault(section, {}).update(values)

    if not found_file:
        return ConfigLoadResult(ConfigStatus.ABSENT, {}, ())

    unknown = unknown_config_keys(merged)
    for item in unknown:
        diagnostics.append(ConfigDiagnostic("<merged>", item, ConfigStatus.UNKNOWN_KEY))

    if any(d.kind is ConfigStatus.INVALID_TYPE for d in diagnostics):
        return ConfigLoadResult(ConfigStatus.INVALID_TYPE, merged, tuple(diagnostics))
    if unknown:
        # Unknown keys: keep config for doctor, but status is UNKNOWN_KEY
        return ConfigLoadResult(ConfigStatus.UNKNOWN_KEY, merged, tuple(diagnostics))
    return ConfigLoadResult(ConfigStatus.VALID, merged, tuple(diagnostics))


def load_config_result(
    *,
    wordlist: Path | None = None,
    reload: bool = False,
) -> ConfigLoadResult:
    global _settings_cache, _settings_cache_key
    cache_key = tuple(str(p) for p in config_paths(wordlist=wordlist))
    if reload:
        clear_settings_cache()
    if _settings_cache is not None and _settings_cache_key == cache_key:
        return _settings_cache
    _settings_cache = _load_config_uncached(wordlist=wordlist)
    _settings_cache_key = cache_key
    return _settings_cache


def config_blocks_mutating(result: ConfigLoadResult) -> bool:
    """True when pull, push, or recover must abort due to invalid config."""
    return result.status in (
        ConfigStatus.SYNTAX_ERROR,
        ConfigStatus.INVALID_TYPE,
        ConfigStatus.UNKNOWN_KEY,
        ConfigStatus.UNSUPPORTED_SCHEMA,
    )


def load_user_settings_with_issues(
    *,
    wordlist: Path | None = None,
    reload: bool = False,
) -> tuple[Dict[str, Dict[str, Any]], list[str]]:
    scoped = _active_settings.get()
    if scoped is not None and wordlist is None and not reload:
        return scoped, []
    result = load_config_result(wordlist=wordlist, reload=reload)
    issues = [d.message for d in result.diagnostics]
    if result.config is None:
        return {}, issues
    return result.config, issues


def load_user_settings(
    *,
    wordlist: Path | None = None,
    reload: bool = False,
) -> Dict[str, Dict[str, Any]]:
    scoped = _active_settings.get()
    if scoped is not None and wordlist is None and not reload:
        return scoped
    settings, _issues = load_user_settings_with_issues(wordlist=wordlist, reload=reload)
    return settings


def unknown_config_keys(settings: Mapping[str, Mapping[str, Any]]) -> list[str]:
    unknown: list[str] = []
    for section, values in settings.items():
        allowed = KNOWN_KEYS.get(section)
        if allowed is None:
            unknown.append(f"[{section}]: unknown section")
            continue
        for key in values.keys():
            if key not in allowed:
                unknown.append(f"[{section}] {key}: unknown key")
    return unknown


def all_known_sections() -> Iterable[str]:
    return KNOWN_KEYS.keys()


def _section_bool(
    settings: Dict[str, Dict[str, Any]],
    section: str,
    key: str,
    default: bool,
) -> bool:
    value = settings.get(section, {}).get(key)
    if isinstance(value, bool):
        return value
    return default


def _section_int(
    settings: Dict[str, Dict[str, Any]],
    section: str,
    key: str,
    default: int,
) -> int:
    value = settings.get(section, {}).get(key)
    if isinstance(value, int):
        return value
    return default


def dictionary_flag(
    settings: Dict[str, Dict[str, Any]],
    key: str,
    default: bool,
) -> bool:
    return _section_bool(settings, "dictionaries", key, default)


def push_int(key: str, default: int) -> int:
    return _section_int(load_user_settings(), "push", key, default)


def push_flag(key: str, default: bool) -> bool:
    return _section_bool(load_user_settings(), "push", key, default)


def io_int(key: str, default: int) -> int:
    return _section_int(load_user_settings(), "io", key, default)


def neovim_flag(key: str, default: bool) -> bool:
    return _section_bool(load_user_settings(), "neovim", key, default)
