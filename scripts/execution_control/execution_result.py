"""Transient execution results separating functional raw output from retained evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ControlledExecutionResult:
    """In-process execution outcome. Raw tails never belong in retained artifacts."""

    exit_code: int
    raw_stdout_tail: str
    raw_stderr_tail: str
    sanitized_stdout_tail: str
    sanitized_stderr_tail: str
    timing: dict[str, Any]

    @property
    def raw_output(self) -> str:
        return self.raw_stdout_tail + self.raw_stderr_tail

    @property
    def sanitized_output(self) -> str:
        return self.sanitized_stdout_tail + self.sanitized_stderr_tail
