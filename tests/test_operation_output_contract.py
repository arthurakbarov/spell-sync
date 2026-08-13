"""Contract: every in-scope CLI command uses operation_presenter."""

import ast
import unittest
from pathlib import Path

from spell_sync.cli import COMMANDS

# Must match operation_presenter / IN_SCOPE_COMMANDS exemptions in this module.
IN_SCOPE_COMMANDS = frozenset(
    {
        "config-check",
        "doctor",
        "git-save",
        "init",
        "lint",
        "plan",
        "pull",
        "push",
        "recover",
        "status",
        "support-report",
    }
)
EXEMPT_COMMANDS = frozenset({"version", "ui"})

_ROOT = Path(__file__).resolve().parents[1]
_SPELL_SYNC = _ROOT / "spell_sync"


def _module_source_for_command(name: str) -> str:
    fn = COMMANDS[name]
    module_file = Path(fn.__code__.co_filename)
    return module_file.read_text(encoding="utf-8")


def _operation_specs_in_source(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "OperationSpec":
            calls.append(node)
        elif isinstance(func, ast.Attribute) and func.attr == "OperationSpec":
            calls.append(node)
    return calls


def _kw_str(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg != name:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


class TestOperationOutputContract(unittest.TestCase):
    def test_command_registry_partition(self) -> None:
        registered = frozenset(COMMANDS)
        self.assertEqual(registered, IN_SCOPE_COMMANDS | EXEMPT_COMMANDS)
        self.assertFalse(IN_SCOPE_COMMANDS & EXEMPT_COMMANDS)

    def test_in_scope_commands_use_operation_session(self) -> None:
        for name in sorted(IN_SCOPE_COMMANDS):
            source = _module_source_for_command(name)
            with self.subTest(command=name):
                self.assertIn(
                    "operation_session",
                    source,
                    f"{name} must call operation_session (see operation_presenter)",
                )
                self.assertIn("OperationSpec", source)

    def test_exempt_commands_do_not_require_presenter(self) -> None:
        for name in sorted(EXEMPT_COMMANDS):
            source = _module_source_for_command(name)
            with self.subTest(command=name):
                # Allowed to mention the doc; must not open a session.
                self.assertNotIn("operation_session(", source)

    def test_operation_specs_declare_product_activity(self) -> None:
        seen_keys: set[str] = set()
        for name in sorted(IN_SCOPE_COMMANDS):
            source = _module_source_for_command(name)
            specs = _operation_specs_in_source(source)
            self.assertGreater(len(specs), 0, f"{name}: expected OperationSpec(...)")
            for call in specs:
                key = _kw_str(call, "key")
                activity = _kw_str(call, "activity")
                with self.subTest(command=name, key=key):
                    self.assertIsNotNone(key)
                    self.assertIsNotNone(
                        activity,
                        f"{name}: OperationSpec(key={key!r}) must set activity= for hang copy",
                    )
                    assert activity is not None
                    self.assertTrue(activity.strip())
                    self.assertNotEqual(activity.strip(), key)
                    # Hang label should not be the raw CLI verb alone when longer product
                    # phrasing exists — at minimum it must contain a space or be Title Case.
                    self.assertTrue(
                        " " in activity or activity[:1].isupper(),
                        f"activity={activity!r} should be product language",
                    )
                    seen_keys.add(key or "")
        # Core mutation/preview keys must appear somewhere among in-scope specs.
        for required in ("pull", "push", "recover", "status", "lint"):
            self.assertIn(required, seen_keys)

    def test_guest_operation_output_doc_explains_progress(self) -> None:
        doc = (_SPELL_SYNC.parent / "docs" / "OPERATION_OUTPUT.md").read_text(encoding="utf-8")
        lowered = doc.lower()
        self.assertIn("usually takes about", lowered)
        self.assertIn("progress", lowered)
        self.assertIn("--json", lowered)
        self.assertIn("`spell-sync version`", doc)
        self.assertIn("`spell-sync ui`", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
