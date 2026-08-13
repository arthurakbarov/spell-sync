"""Packaged target validation metadata for runtime surfaces."""

import json
from importlib import resources
from typing import Any


def load_packaged_target_validation() -> dict[str, Any] | None:
    """Load bundled validation JSON without reading repository docs."""
    try:
        payload_text = (
            resources.files("spell_sync.bundled")
            .joinpath("target-validation.json")
            .read_text(encoding="utf-8")
        )
        payload = json.loads(payload_text)
    except OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload
