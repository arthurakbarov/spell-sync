"""Shared application service dependencies."""

from dataclasses import dataclass

from ...diagnostics.history_store import OperationHistoryStore
from ...diagnostics.paths import AppStatePaths
from ..runtime_resolver import RuntimeResolver


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    runtime: RuntimeResolver
    history_store: OperationHistoryStore
    state_paths: AppStatePaths
