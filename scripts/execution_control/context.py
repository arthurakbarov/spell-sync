"""Normalized execution context for duration prediction."""

from __future__ import annotations

import platform
import sys

from .models import NormalizedContext


def workload_bucket(
    *, test_file_count: int = 0, test_node_count: int = 0, child_count: int = 0
) -> str:
    count = test_node_count or test_file_count or child_count
    if count <= 1:
        return "1"
    if count <= 5:
        return "2-5"
    if count <= 20:
        return "6-20"
    if count <= 100:
        return "21-100"
    if count <= 500:
        return "101-500"
    return "501+"


def platform_family() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    if system == "windows":
        return "windows"
    return system or "unknown"


def build_context(
    *,
    execution_mode: str,
    test_file_count: int = 0,
    test_node_count: int = 0,
    child_count: int = 0,
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
    environment: str = "unknown",
) -> NormalizedContext:
    major, minor = sys.version_info.major, sys.version_info.minor
    return NormalizedContext(
        platform=platform_family(),
        python_version=f"{major}.{minor}",
        execution_mode=execution_mode,
        workload_bucket=workload_bucket(
            test_file_count=test_file_count,
            test_node_count=test_node_count,
            child_count=child_count,
        ),
        coverage=coverage,
        tui=tui,
        packaging=packaging,
        environment=environment,
    )
