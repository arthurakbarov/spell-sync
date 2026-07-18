"""UI-neutral operation events for CLI and TUI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class OperationKind(str, Enum):
    STATUS = "status"
    PLAN = "plan"
    PULL = "pull"
    PUSH = "push"
    DOCTOR = "doctor"
    RECOVER = "recover"
    SETUP = "setup"


class EventLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class OperationEvent:
    operation: OperationKind
    stage: str
    message: str
    level: EventLevel = EventLevel.INFO
    target: str | None = None
    completed: int | None = None
    total: int | None = None


class EventSink(Protocol):
    def __call__(self, event: OperationEvent) -> None: ...
