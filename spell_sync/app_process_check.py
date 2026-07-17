"""Browser/app process detection, push prompts, and TOCTOU skip logic."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from .config import CONFIRM_YES, enable_chrome, enable_edge, enable_firefox, enable_obsidian
from .log import log
from .paths import (
    chrome_dict_paths,
    edge_dict_paths,
    firefox_dict_paths,
    is_windows,
    obsidian_dict_paths,
)
from .subprocess_utils import trim_subprocess_text

# True — running, False — not running, None — check failed.
RunningState = Optional[bool]
ChromeState = RunningState
FirefoxState = RunningState
ObsidianState = RunningState
PushPromptFn = Callable[[], Optional[bool]]


def _pgrep_running(returncode: int) -> RunningState:
    if returncode == 0:
        return True
    if returncode == 1:
        return False
    return None


def _windows_exe_running(exe_name: str) -> RunningState:
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=flags,
        )
        if result.returncode != 0:
            err = trim_subprocess_text(result.stderr or "")
            if err:
                log.detail(f"tasklist failed: {err}")
            return None
        return exe_name.lower() in (result.stdout or "").lower()
    except (OSError, subprocess.TimeoutExpired):
        return None


def _macos_pgrep_exact(process_name: str) -> RunningState:
    try:
        result = subprocess.run(
            ["pgrep", "-x", process_name],
            capture_output=True,
            timeout=5,
        )
        return _pgrep_running(result.returncode)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _macos_pgrep_first_running(*patterns: str) -> RunningState:
    saw_unknown = False
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-x", pattern],
                capture_output=True,
                timeout=5,
            )
            state = _pgrep_running(result.returncode)
            if state is True:
                return True
            if state is None:
                saw_unknown = True
        except (OSError, subprocess.TimeoutExpired):
            saw_unknown = True
    if saw_unknown:
        return None
    return False


def _linux_pgrep_first_resolved(*names: str) -> RunningState:
    saw_unknown = False
    for name in names:
        try:
            result = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True,
                timeout=5,
            )
            state = _pgrep_running(result.returncode)
            if state is True:
                return True
            if state is None:
                saw_unknown = True
        except (OSError, subprocess.TimeoutExpired):
            saw_unknown = True
    if saw_unknown:
        return None
    return False


def is_chrome_running() -> ChromeState:
    if is_windows():
        return _windows_exe_running("chrome.exe")
    if sys.platform == "darwin":
        return _macos_pgrep_exact("Google Chrome")
    return _linux_pgrep_first_resolved(
        "chrome",
        "google-chrome",
        "google-chrome-stable",
    )


def is_edge_running() -> ChromeState:
    if is_windows():
        return _windows_exe_running("msedge.exe")
    if sys.platform == "darwin":
        return _macos_pgrep_exact("Microsoft Edge")
    return _linux_pgrep_first_resolved(
        "msedge",
        "microsoft-edge",
        "microsoft-edge-stable",
    )


def is_firefox_running() -> FirefoxState:
    if is_windows():
        return _windows_exe_running("firefox.exe")
    if sys.platform == "darwin":
        return _macos_pgrep_first_running("firefox", "Firefox")
    return _linux_pgrep_first_resolved("firefox", "Firefox", "firefox-esr")


def is_obsidian_running() -> ObsidianState:
    if is_windows():
        return _windows_exe_running("Obsidian.exe")
    if sys.platform == "darwin":
        return _macos_pgrep_exact("Obsidian")
    return _linux_pgrep_first_resolved("obsidian", "Obsidian")


def chrome_dictionaries_enabled() -> bool:
    return enable_chrome() and bool(chrome_dict_paths())


def edge_dictionaries_enabled() -> bool:
    return enable_edge() and bool(edge_dict_paths())


def firefox_dictionaries_enabled() -> bool:
    return enable_firefox() and bool(firefox_dict_paths())


def obsidian_dictionaries_enabled() -> bool:
    return enable_obsidian() and bool(obsidian_dict_paths())


def _confirm_risky_push(*, interactive: bool, reason: str, close_hint: str) -> Optional[bool]:
    log.warn(reason)
    log.detail(close_hint)
    if not interactive:
        return True
    try:
        answer = input("Continue push? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return None
    return answer in CONFIRM_YES


def _confirm_app_before_push(
    *,
    interactive: bool,
    enabled: bool,
    is_running: RunningState,
    close_hint: str,
    running_reason: str,
    check_failed_reason: str,
) -> Optional[bool]:
    if not enabled:
        return True

    state = is_running
    if state is False:
        return True
    if state is None:
        return _confirm_risky_push(
            interactive=interactive,
            reason=check_failed_reason,
            close_hint=close_hint,
        )
    return _confirm_risky_push(
        interactive=interactive,
        reason=running_reason,
        close_hint=close_hint,
    )


def confirm_chrome_before_push(*, interactive: bool) -> Optional[bool]:
    """True — continue push, False — cancel, None — interrupted (Ctrl+C)."""
    return _confirm_app_before_push(
        interactive=interactive,
        enabled=chrome_dictionaries_enabled(),
        is_running=is_chrome_running(),
        close_hint="Close Chrome or continue push at your own risk.",
        running_reason="Google Chrome is running — dictionary may be overwritten on exit.",
        check_failed_reason=("Could not check whether Chrome is running — push at your own risk."),
    )


def confirm_edge_before_push(*, interactive: bool) -> Optional[bool]:
    """True — continue push, False — cancel, None — interrupted (Ctrl+C)."""
    return _confirm_app_before_push(
        interactive=interactive,
        enabled=edge_dictionaries_enabled(),
        is_running=is_edge_running(),
        close_hint="Close Edge or continue push at your own risk.",
        running_reason="Microsoft Edge is running — dictionary may be overwritten on exit.",
        check_failed_reason=("Could not check whether Edge is running — push at your own risk."),
    )


def confirm_firefox_before_push(*, interactive: bool) -> Optional[bool]:
    """True — continue push, False — cancel, None — interrupted (Ctrl+C)."""
    return _confirm_app_before_push(
        interactive=interactive,
        enabled=firefox_dictionaries_enabled(),
        is_running=is_firefox_running(),
        close_hint="Close Firefox or continue push at your own risk.",
        running_reason="Firefox is running — persdict.dat may be overwritten on exit.",
        check_failed_reason=("Could not check whether Firefox is running — push at your own risk."),
    )


def confirm_obsidian_before_push(*, interactive: bool) -> Optional[bool]:
    """True — continue push, False — cancel, None — interrupted (Ctrl+C)."""
    return _confirm_app_before_push(
        interactive=interactive,
        enabled=obsidian_dictionaries_enabled(),
        is_running=is_obsidian_running(),
        close_hint="Close Obsidian or continue push at your own risk.",
        running_reason=("Obsidian is running — Custom Dictionary.txt may be overwritten on exit."),
        check_failed_reason=(
            "Could not check whether Obsidian is running — push at your own risk."
        ),
    )


# --- TOCTOU skip for non-interactive push ---


@dataclass(frozen=True)
class _RunningAppRule:
    label: str
    enabled: Callable[[], bool]
    is_running: Callable[[], Optional[bool]]
    name_prefix: str


_RUNNING_APP_RULES = (
    _RunningAppRule(
        "Google Chrome",
        lambda: chrome_dictionaries_enabled(),
        lambda: is_chrome_running(),
        "chrome:",
    ),
    _RunningAppRule(
        "Microsoft Edge",
        lambda: edge_dictionaries_enabled(),
        lambda: is_edge_running(),
        "edge:",
    ),
    _RunningAppRule(
        "Firefox",
        lambda: firefox_dictionaries_enabled(),
        lambda: is_firefox_running(),
        "firefox:",
    ),
    _RunningAppRule(
        "Obsidian",
        lambda: obsidian_dictionaries_enabled(),
        lambda: is_obsidian_running(),
        "obsidian",
    ),
)


def _dictionary_matches_rule(name: str, prefix: str) -> bool:
    if prefix.endswith(":"):
        return name.startswith(prefix)
    return name == prefix


def _running_state_reason(label: str, state: Optional[bool]) -> str:
    if state is True:
        return f"{label} is running"
    return f"could not verify {label} is quit"


def running_app_skip_reasons(dictionary_names: Sequence[str]) -> dict[str, str]:
    """Mapping of dictionary name -> skip reason (no logging)."""
    reasons: dict[str, str] = {}
    for rule in _RUNNING_APP_RULES:
        if not rule.enabled():
            continue
        state = rule.is_running()
        if state is False:
            continue
        matching = {
            name for name in dictionary_names if _dictionary_matches_rule(name, rule.name_prefix)
        }
        if not matching:
            continue
        reason = _running_state_reason(rule.label, state)
        for name in matching:
            reasons[name] = reason
    return reasons


def running_app_skip_names(dictionary_names: Sequence[str]) -> frozenset[str]:
    """Dictionary names to skip because the parent app is running or unknown (no logging)."""
    return frozenset(running_app_skip_reasons(dictionary_names))
