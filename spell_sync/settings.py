"""Load spell-sync.toml with identical semantics on all supported Python versions."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .runtime_settings import RuntimeSettings

_CONFIG_FILENAME = "spell-sync.toml"

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
            "sublime",
            "jetbrains",
            "hunspell",
            "obsidian",
            "libreoffice",
            "macos_spelling",
            "win_spelling",
            # Exact dictionary names excluded while their family stays enabled.
            "excluded",
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


class ConfigStatus(StrEnum):
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
    config: dict[str, dict[str, Any]] | None
    diagnostics: tuple[ConfigDiagnostic, ...]

    def runtime_settings(self) -> RuntimeSettings:
        if self.config is None:
            return RuntimeSettings.defaults()
        return RuntimeSettings.from_config_dict(self.config)


def _parse_toml_with_issues(path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Parse one TOML file with standard-library tomllib."""
    issues: list[str] = []
    label = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        issues.append(f"{label}: unreadable")
        return {}, issues
    except UnicodeError:
        issues.append(f"{label}: undecodable")
        return {}, issues
    try:
        # Always pass str: tomllib.loads rejects bytes (TypeError on 3.11+).
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        issues.append(f"{label}: {exc}")
        return {}, issues
    except TypeError:  # pragma: no cover -- defensive
        issues.append(f"{label}: unsupported value type")
        return {}, issues

    data: dict[str, dict[str, Any]] = {}
    for section, values in parsed.items():
        if not isinstance(values, dict):
            issues.append(f"{label}: [{section}] must be a table")
            continue
        section_data: dict[str, Any] = {}
        for key, value in values.items():
            if isinstance(value, (bool, int)):
                section_data[key] = value
            elif isinstance(value, list):
                if not all(isinstance(item, str) for item in value):
                    issues.append(f"{label}: [{section}] {key}: array values must be strings")
                    continue
                section_data[key] = list(value)
            else:
                issues.append(f"{label}: [{section}] {key}: unsupported value type")
        if section_data:
            data[section] = section_data
    return data, issues


def project_config_path(wordlist: Path | None = None) -> Path:
    """Sole config path: ``spell-sync.toml`` beside the effective wordlist.

    When *wordlist* is ``None``, use ``project_root() / spell-sync.toml``.
    """
    if wordlist is not None:
        return wordlist.resolve().parent / _CONFIG_FILENAME
    from .paths import project_root

    return project_root() / _CONFIG_FILENAME


def _load_config_uncached(*, wordlist: Path | None = None) -> ConfigLoadResult:
    path = project_config_path(wordlist)
    path_str = str(path)
    if not path.is_file():
        return ConfigLoadResult(ConfigStatus.ABSENT, {}, ())

    data, file_issues = _parse_toml_with_issues(path)
    diagnostics: list[ConfigDiagnostic] = []
    for issue in file_issues:
        if "unsupported value type" in issue or "must be a table" in issue:
            kind = ConfigStatus.INVALID_TYPE
        else:
            kind = ConfigStatus.SYNTAX_ERROR
        diagnostics.append(ConfigDiagnostic(path_str, issue, kind))
    if file_issues and not data:
        # Hard syntax error — fail closed
        return ConfigLoadResult(
            ConfigStatus.SYNTAX_ERROR,
            None,
            tuple(diagnostics),
        )

    unknown = unknown_config_keys(data)
    diagnostics.extend(
        ConfigDiagnostic(path_str, item, ConfigStatus.UNKNOWN_KEY) for item in unknown
    )

    if any(d.kind is ConfigStatus.INVALID_TYPE for d in diagnostics):
        return ConfigLoadResult(ConfigStatus.INVALID_TYPE, data, tuple(diagnostics))
    if unknown:
        # Unknown keys: keep config for doctor, but status is UNKNOWN_KEY
        return ConfigLoadResult(ConfigStatus.UNKNOWN_KEY, data, tuple(diagnostics))
    return ConfigLoadResult(ConfigStatus.VALID, data, tuple(diagnostics))


def load_config_result(
    *,
    wordlist: Path | None = None,
) -> ConfigLoadResult:
    return _load_config_uncached(wordlist=wordlist)


def config_blocks_mutating(result: ConfigLoadResult) -> bool:
    """True when pull, push, or recover must abort due to invalid config."""
    return result.status in (
        ConfigStatus.SYNTAX_ERROR,
        ConfigStatus.INVALID_TYPE,
        ConfigStatus.UNKNOWN_KEY,
        ConfigStatus.UNSUPPORTED_SCHEMA,
    )


def load_project_settings_with_issues(
    *,
    wordlist: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    result = load_config_result(wordlist=wordlist)
    issues = [d.message for d in result.diagnostics]
    if result.config is None:
        return {}, issues
    return result.config, issues


def unknown_config_keys(settings: Mapping[str, Mapping[str, Any]]) -> list[str]:
    unknown: list[str] = []
    for section, values in settings.items():
        allowed = KNOWN_KEYS.get(section)
        if allowed is None:
            unknown.append(f"[{section}]: unknown section")
            continue
        unknown.extend(f"[{section}] {key}: unknown key" for key in values if key not in allowed)
    return unknown
