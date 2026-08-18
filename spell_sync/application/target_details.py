"""Target capability details for TUI and support surfaces."""

from dataclasses import dataclass

from ..project_setup.discovery import SetupTarget
from ..support.path_redaction import redact_path, redact_profile_label
from ..target_capabilities import (
    TargetCapability,
    TargetFilterKind,
    capability_for_discovery_target,
    resolve_capability_identifier,
)
from ..target_validation import load_packaged_target_validation
from .field_blocks import format_indented_fields
from .product_concepts import (
    COLLECT_WORDS_LABEL,
    FULL_WORD_LIST_FILTER_LABEL,
    PUSH_FILTERING_NOTICE,
    UPDATE_APPS_LABEL,
)


@dataclass(frozen=True)
class TargetValidationStatus:
    automated_validation: str
    manual_validation: str
    last_real_app_test: str | None


@dataclass(frozen=True)
class TargetDetailsSnapshot:
    identifier: str
    display_name: str
    profile_label: str | None
    enabled: bool
    detected: bool
    readable: bool
    writable: bool
    runtime_state: str
    pull_supported: bool
    push_supported: bool
    filtering_label: str
    profile_model: str
    close_policy_label: str
    recovery_protected: bool
    discovery_source: str
    custom_dictionary_path: str | None
    automated_validation: str
    manual_validation: str
    suggested_action: str | None
    detail: str | None


def _filtering_label(filter_kind: TargetFilterKind) -> str:
    if filter_kind == TargetFilterKind.FULL:
        return FULL_WORD_LIST_FILTER_LABEL
    if filter_kind == TargetFilterKind.LATIN:
        return "Applicable Latin-script personal words"
    if filter_kind == TargetFilterKind.CYRILLIC_AND_NON_LATIN:
        return "Applicable Cyrillic and non-Latin personal words"
    return PUSH_FILTERING_NOTICE.split("\n", 1)[0]


def _close_policy_label(capability: TargetCapability) -> str:
    if capability.close_policy.value == "block-if-running":
        return f"Update my apps is blocked while {capability.display_name} is running"
    return "No running-application block"


def _runtime_state(target: SetupTarget) -> str:
    if not target.supported:
        return "Unsupported on this platform"
    if target.status == "corrupt":
        return "Corrupt"
    if target.status == "unreadable":
        return "Unreadable"
    if not target.detected:
        return "Unavailable"
    if not target.enabled:
        return "Disabled"
    if target.available and target.readable:
        return "Ready"
    return "Needs attention"


def _discovery_source(identifier: str) -> str:
    mapping = {
        "chrome": "Chromium profile discovery",
        "edge": "Chromium profile discovery",
        "brave": "Chromium profile discovery",
        "vivaldi": "Chromium profile discovery",
        "firefox": "Firefox profile discovery",
        "editors": "Editor custom dictionary discovery",
        "jetbrains": "JetBrains custom dictionary discovery",
        "macos_spelling": "macOS custom spelling files",
        "win_spelling": "Windows custom spelling files",
    }
    return mapping.get(identifier, "Application custom dictionary discovery")


def _load_validation_lookup() -> dict[tuple[str, str], TargetValidationStatus]:
    payload = load_packaged_target_validation()
    if payload is None:
        return {}
    rows = payload.get("targets", [])
    lookup: dict[tuple[str, str], TargetValidationStatus] = {}
    if not isinstance(rows, list):
        return lookup
    import platform

    system = platform.system()
    if system == "Darwin":
        current = "macos"
    elif system == "Windows":
        current = "windows"
    else:
        current = "linux"
    for row in rows:
        if not isinstance(row, dict):
            continue
        target_id = row.get("target_id")
        row_platform = row.get("platform")
        if not isinstance(target_id, str) or not isinstance(row_platform, str):
            continue
        if row_platform != current:
            continue
        lookup[(target_id, row_platform)] = TargetValidationStatus(
            automated_validation=str(row.get("automated_validation", "not-run")),
            manual_validation=str(row.get("manual_validation", "not-run")),
            last_real_app_test=(
                str(row["tested_on"]) if row.get("tested_on") is not None else None
            ),
        )
    return lookup


def build_target_details(
    target: SetupTarget,
    *,
    profile_index: int = 0,
    suggested_action: str | None = None,
) -> TargetDetailsSnapshot:
    capability = capability_for_discovery_target(target.identifier)
    if capability is None:
        raise ValueError(f"No capability descriptor for target {target.identifier}")
    validation = _load_validation_lookup().get(
        (target.identifier, _current_platform()),
        TargetValidationStatus("not-run", "not-run", None),
    )
    writable = (
        target.available
        and target.readable
        and target.supported
        and target.status
        not in {
            "corrupt",
            "unreadable",
            "unsupported",
        }
    )
    return TargetDetailsSnapshot(
        identifier=resolve_capability_identifier(target.identifier),
        display_name=capability.display_name,
        profile_label=redact_profile_label(target.identifier, profile_index),
        enabled=target.enabled,
        detected=target.detected,
        readable=target.readable,
        writable=writable,
        runtime_state=_runtime_state(target),
        pull_supported=capability.pull_supported,
        push_supported=capability.push_supported,
        filtering_label=_filtering_label(capability.filter_kind),
        profile_model=capability.profile_model.value,
        close_policy_label=_close_policy_label(capability),
        recovery_protected=capability.recovery_protected,
        discovery_source=_discovery_source(target.identifier),
        custom_dictionary_path=redact_path(str(target.path)) if target.path else None,
        automated_validation=validation.automated_validation,
        manual_validation=validation.manual_validation,
        suggested_action=suggested_action,
        detail=target.detail,
    )


def _current_platform() -> str:
    import platform

    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Windows":
        return "windows"
    return "linux"


def format_target_details_text(details: TargetDetailsSnapshot) -> str:
    title = details.display_name
    if details.profile_label:
        title = f"{title} · {details.profile_label}"
    discovery_rows: list[tuple[str, object]] = [
        ("Source", details.discovery_source),
    ]
    if details.custom_dictionary_path:
        discovery_rows.append(("Custom dictionary", details.custom_dictionary_path))
    lines = [
        title,
        "",
        "State",
        *format_indented_fields(
            [
                ("Enabled", "Yes" if details.enabled else "No"),
                ("Detected", "Yes" if details.detected else "No"),
                ("Readable", "Yes" if details.readable else "No"),
                ("Writable", "Yes" if details.writable else "No"),
                ("Status", details.runtime_state),
            ]
        ),
        "",
        "Capabilities",
        *format_indented_fields(
            [
                (
                    COLLECT_WORDS_LABEL,
                    "Supported" if details.pull_supported else "Not supported",
                ),
                (
                    UPDATE_APPS_LABEL,
                    "Supported" if details.push_supported else "Not supported",
                ),
                ("Filtering", details.filtering_label),
                ("Profiles", details.profile_model),
                ("Running application", details.close_policy_label),
                (
                    "Recovery protection",
                    "Enabled" if details.recovery_protected else "Disabled",
                ),
            ]
        ),
        "",
        "Discovery",
        *format_indented_fields(discovery_rows),
        "",
        "Validation",
        *format_indented_fields(
            [
                ("Automated fixtures", details.automated_validation),
                ("Real application test", details.manual_validation),
            ]
        ),
    ]
    if details.suggested_action:
        lines.extend(["", details.suggested_action])
    return "\n".join(lines)
