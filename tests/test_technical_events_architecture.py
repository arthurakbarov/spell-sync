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
        frozen, slots = _dataclass_flags(_EVENTS_PY, "TechnicalEvent")
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

    def test_emit_technical_routes_through_operation_emitter(self) -> None:
        from spell_sync.application.services import _shared

        source = inspect.getsource(_shared.emit_technical)
        self.assertIn("operation_emitter", source)
        self.assertNotIn("EventEmitter(", source)
