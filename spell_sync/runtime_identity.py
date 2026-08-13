"""Immutable runtime identity for preview/execution consistency checks."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .dictionaries import Dictionary
from .runtime_settings import RuntimeSettings
from .settings import ConfigLoadResult, project_config_path
from .sync_context import RuntimeContext
from .target_capabilities import DICTIONARY_FILTER_KINDS, TargetFilterKind


@dataclass(frozen=True, slots=True)
class ConfigInputFingerprint:
    path: Path
    exists: bool
    sha256: str | None


@dataclass(frozen=True, slots=True)
class TargetIdentity:
    target_id: str
    path: Path
    format: str
    subset_policy: str


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    wordlist: Path
    project_dir: Path
    config_input: ConfigInputFingerprint
    settings: RuntimeSettings
    targets: tuple[TargetIdentity, ...]
    strict_push: bool


def _config_input_fingerprint(wordlist: Path) -> ConfigInputFingerprint:
    path = project_config_path(wordlist)
    resolved = path.resolve()
    exists = path.is_file()
    digest: str | None = None
    if exists:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return ConfigInputFingerprint(resolved, exists, digest)


def _subset_policy_for(dictionary: Dictionary) -> str:
    kind = DICTIONARY_FILTER_KINDS.get(dictionary.name)
    if kind is not None:
        return kind.value
    if dictionary.subset is None:
        return TargetFilterKind.FULL.value
    return dictionary.subset.__name__


def _target_identities(dictionaries: tuple[Dictionary, ...]) -> tuple[TargetIdentity, ...]:
    identities = [
        TargetIdentity(
            target_id=dictionary.name,
            path=Path(dictionary.path).resolve(),
            format=dictionary.format.value,
            subset_policy=_subset_policy_for(dictionary),
        )
        for dictionary in dictionaries
    ]
    return tuple(sorted(identities, key=lambda item: item.target_id))


def build_runtime_identity(
    context: RuntimeContext,
    *,
    config_result: ConfigLoadResult | None = None,
) -> RuntimeIdentity:
    """Build deterministic runtime identity from one resolved context."""
    del config_result  # config input is fingerprinted from the project path
    return RuntimeIdentity(
        wordlist=context.wordlist.resolve(),
        project_dir=context.project_dir.resolve(),
        config_input=_config_input_fingerprint(context.wordlist),
        settings=context.settings,
        targets=_target_identities(context.dictionaries),
        strict_push=context.strict_push,
    )
