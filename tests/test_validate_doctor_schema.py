"""Doctor schema CI entrypoint must validate a real payload, not schema-only."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "scripts" / "validate_doctor_schema.py"

_spec = importlib.util.spec_from_file_location("validate_doctor_schema", MOD_PATH)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_default_entrypoint_validates_example_payload() -> None:
    assert mod.main([]) == 0


def test_required_keys_match_schema() -> None:
    assert tuple(mod.REQUIRED_KEYS) == mod.schema_required_keys()


def test_real_doctor_command_payload_validates() -> None:
    from spell_sync.health.serialize import doctor_command_payload
    from spell_sync.health.types import CliStatus, DoctorReport
    from spell_sync.json_output import base_payload

    report = DoctorReport(
        wordlist_path="wordlist.txt",
        wordlist_count=1,
        package_version="1.0.0",
        skipped_unreadable=(),
        git_hooks=None,
        cli=CliStatus(
            on_path=True,
            argv=("spell-sync",),
            executable="spell-sync",
            pip_script=None,
            path_export=None,
        ),
        actions=(),
        checks=(),
        dictionaries_total=0,
        dictionaries_readable=0,
        dictionaries_writable=0,
        max_drift_add=0,
        max_drift_remove=0,
    )
    payload = doctor_command_payload(report, health_check=False)
    payload.update(base_payload("doctor", exit=0))
    assert mod.validate_doctor_payload(payload) == []


def test_payload_validator_rejects_home_path() -> None:
    payload = json.loads(mod.DEFAULT_PAYLOAD.read_text(encoding="utf-8"))
    payload["checks"] = [
        {"level": "info", "message": "path /Users/someone/secret"},
    ]
    errors = mod.validate_doctor_payload(payload)
    assert "privacy:absolute-home-path" in errors


def test_payload_validator_rejects_action_count_mismatch() -> None:
    payload = json.loads(mod.DEFAULT_PAYLOAD.read_text(encoding="utf-8"))
    payload["actions"] = [{"id": "x", "reason": "y", "optional": False}]
    payload["required_action_count"] = 0
    errors = mod.validate_doctor_payload(payload)
    assert "required_action_count:mismatch" in errors


def test_payload_validator_rejects_null_action_count() -> None:
    payload = json.loads(mod.DEFAULT_PAYLOAD.read_text(encoding="utf-8"))
    payload["required_action_count"] = None
    errors = mod.validate_doctor_payload(payload)
    assert "required_action_count:int" in errors
