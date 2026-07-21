"""Architecture guards for typed technical events (Phase 5)."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from spell_sync.application.events import (
    EventId,
    operation_emitter,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPELL_SYNC = _REPO_ROOT / "spell_sync"
_EVENTS_PY = _SPELL_SYNC / "application" / "events.py"
_TECHNICAL_EVENT_MODEL = _SPELL_SYNC / "diagnostics" / "technical_event_model.py"
_EVENT_METADATA = _SPELL_SYNC / "diagnostics" / "event_metadata.py"
_PROJECT_SETUP = _SPELL_SYNC / "project_setup"
_OPERATION_SCREEN = _SPELL_SYNC / "tui" / "screens" / "operation_screen.py"
_APPLICATION_SERVICES = _SPELL_SYNC / "application" / "services"


def _dataclass_flags(path: Path, class_name: str) -> tuple[bool, bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            frozen = False
            slots = False
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
                    frozen = False
                    slots = False
                elif isinstance(decorator, ast.Call):
                    func = decorator.func
                    if isinstance(func, ast.Name) and func.id == "dataclass":
                        for keyword in decorator.keywords:
                            if keyword.arg == "frozen":
                                frozen = isinstance(keyword.value, ast.Constant) and bool(
                                    keyword.value.value
                                )
                            if keyword.arg == "slots":
                                slots = isinstance(keyword.value, ast.Constant) and bool(
                                    keyword.value.value
                                )
            return frozen, slots
    raise AssertionError(f"{class_name} not found in {path}")


def _class_has_field(path: Path, class_name: str, field_name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == field_name:
                        return True
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == field_name:
                            return True
    return False


def _application_service_sources() -> list[Path]:
    return sorted(_APPLICATION_SERVICES.glob("*.py"))


class TestTechnicalEventsArchitecture(unittest.TestCase):
    def test_technical_event_is_frozen_with_slots(self) -> None:
        frozen, slots = _dataclass_flags(_TECHNICAL_EVENT_MODEL, "TechnicalEvent")
        self.assertTrue(frozen, msg="[ARCH-TE-001] TechnicalEvent must be frozen")
        self.assertTrue(slots, msg="[ARCH-TE-002] TechnicalEvent must use slots")

    def test_presented_event_is_frozen_with_slots(self) -> None:
        frozen, slots = _dataclass_flags(_EVENTS_PY, "PresentedEvent")
        self.assertTrue(frozen, msg="[ARCH-TE-003] PresentedEvent must be frozen")
        self.assertTrue(slots, msg="[ARCH-TE-004] PresentedEvent must use slots")

    def test_event_id_values_are_unique(self) -> None:
        values = [item.value for item in EventId]
        self.assertEqual(
            len(values),
            len(set(values)),
            msg="[ARCH-TE-005] EventId values must be unique",
        )

    def test_events_module_has_no_operation_event_with_stage(self) -> None:
        tree = ast.parse(_EVENTS_PY.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "OperationEvent":
                self.fail("[ARCH-TE-006] OperationEvent must not exist in events.py")
        self.assertFalse(
            _class_has_field(_EVENTS_PY, "OperationEvent", "stage"),
            msg="[ARCH-TE-006] OperationEvent.stage must not exist in events.py",
        )

    def test_application_services_do_not_emit_free_form_stage_strings(self) -> None:
        offenders: list[str] = []
        for path in _application_service_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                keywords = {keyword.arg: keyword.value for keyword in node.keywords}
                if "stage" in keywords:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}: stage= keyword")
                func = node.func
                if isinstance(func, ast.Name) and func.id == "TechnicalEvent":
                    for keyword in node.keywords:
                        if keyword.arg == "message":
                            offenders.append(
                                f"{path.relative_to(_REPO_ROOT)}: TechnicalEvent(message=...)"
                            )
        self.assertEqual(
            offenders,
            [],
            msg="[ARCH-TE-007] application services must not emit free-form stage/message strings",
        )

    def test_operation_screen_does_not_compare_event_stage(self) -> None:
        source = _OPERATION_SCREEN.read_text(encoding="utf-8")
        self.assertNotIn(
            "event.stage",
            source,
            msg="[ARCH-TE-008] operation_screen must not compare event.stage",
        )

    def test_operation_emitter_is_canonical_factory(self) -> None:
        self.assertEqual(
            inspect.getfile(operation_emitter),
            str(_EVENTS_PY),
            msg="[ARCH-TE-009] operation_emitter must live in events.py",
        )
        offenders: list[str] = []
        for path in _SPELL_SYNC.rglob("*.py"):
            if path == _EVENTS_PY:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "EventEmitter":
                        rel = path.relative_to(_REPO_ROOT)
                        offenders.append(str(rel))
        self.assertEqual(
            offenders,
            [],
            msg="[ARCH-TE-010] only events.py may construct EventEmitter(...)",
        )

    def test_emit_technical_uses_canonical_emitter(self) -> None:
        from spell_sync.application.services import _shared

        source = inspect.getsource(_shared.emit_technical)
        self.assertIn("emitter.emit", source)
        self.assertNotIn("EventEmitter(", source)

    def test_make_operation_emitter_wraps_operation_emitter(self) -> None:
        from spell_sync.application.services import _shared

        source = inspect.getsource(_shared.make_operation_emitter)
        self.assertIn("operation_emitter", source)

    def test_event_emitter_only_suppresses_technical_sink_exceptions(self) -> None:
        source = (_SPELL_SYNC / "application" / "events.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        emit_method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "EventEmitter"
            for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "emit"
        )
        presentation_in_except = False
        for node in ast.walk(emit_method):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    if handler.type is None or (
                        isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
                    ):
                        for child in ast.walk(handler):
                            if isinstance(child, ast.Call) and isinstance(
                                child.func, ast.Attribute
                            ):
                                if child.func.attr == "presentation_sink" or (
                                    isinstance(child.func.value, ast.Name)
                                    and child.func.value.id == "self"
                                    and child.func.attr in {"presentation_sink", "__call__"}
                                ):
                                    presentation_in_except = True
        for node in ast.walk(emit_method):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Attribute) and func.attr == "presentation_sink":
                    break
        else:
            self.fail("[ARCH-TE-011] presentation sink must be invoked from emit()")
        self.assertFalse(
            presentation_in_except,
            msg="[ARCH-TE-011] presentation sink must not be inside technical except",
        )

    def test_technical_event_uses_typed_metadata_fields(self) -> None:
        self.assertTrue(
            _class_has_field(_TECHNICAL_EVENT_MODEL, "TechnicalEvent", "reason"),
            msg="[ARCH-TE-012] TechnicalEvent.reason must be typed",
        )
        self.assertFalse(
            _class_has_field(_TECHNICAL_EVENT_MODEL, "TechnicalEvent", "reason_code"),
            msg="[ARCH-TE-012] TechnicalEvent must not expose reason_code",
        )

    def test_setup_and_targets_services_always_wire_emitter(self) -> None:
        for name in ("setup.py", "target_settings.py"):
            source = (_APPLICATION_SERVICES / name).read_text(encoding="utf-8")
            self.assertIn(
                "make_operation_emitter",
                source,
                msg=f"[ARCH-TE-013] {name} must use make_operation_emitter",
            )
            self.assertIn(
                "emitter.emit",
                source,
                msg=f"[ARCH-TE-013] {name} must pass emitter.emit to core",
            )

    def test_structured_formatter_writes_pure_json(self) -> None:
        from spell_sync.diagnostics.technical_logging import _SafeFormatter

        source = inspect.getsource(_SafeFormatter.format)
        self.assertIn("structured_event", source)
        self.assertIn("validate_structured_log_message", source)

    def test_no_direct_structured_event_logger_calls_outside_writer(self) -> None:
        writer = _SPELL_SYNC / "diagnostics" / "technical_event_log.py"
        offenders: list[str] = []
        for path in _SPELL_SYNC.rglob("*.py"):
            if path == writer:
                continue
            text = path.read_text(encoding="utf-8")
            if 'extra={"structured_event": True}' in text or "structured_event': True" in text:
                offenders.append(str(path.relative_to(_REPO_ROOT)))
        self.assertEqual(
            offenders,
            [],
            msg="[ARCH-TE-014] only technical_event_log may set structured_event on logger",
        )

    def test_event_metadata_defines_typed_reason_and_outcome(self) -> None:
        text = _EVENT_METADATA.read_text(encoding="utf-8")
        self.assertIn("class EventReason", text)
        self.assertIn("class TerminalOutcome", text)
        self.assertIn("class CorrelationId", text)
        self.assertIn("class TargetId", text)

    def test_project_setup_does_not_import_application_package(self) -> None:
        offenders: list[str] = []
        for path in sorted(_PROJECT_SETUP.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "from ..application." in source or "from spell_sync.application." in source:
                offenders.append(str(path.relative_to(_REPO_ROOT)))
        self.assertEqual(
            offenders,
            [],
            msg="[ARCH-TE-015] project_setup must not import spell_sync.application",
        )
