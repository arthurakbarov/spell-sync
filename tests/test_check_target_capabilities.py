"""Tests for scripts/check_target_capabilities.py marker and write behavior."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_target_capabilities  # noqa: E402

SCRIPT = ROOT / "scripts" / "check_target_capabilities.py"
SUPPORTED_DOC = ROOT / "docs" / "SUPPORTED_APPS.md"
VALIDATION_FILE = ROOT / "docs" / "technical" / "target-validation.json"
START_MARKER = "<!-- target-capabilities:start -->"
END_MARKER = "<!-- target-capabilities:end -->"
OBSOLETE_MATRIX_MARKER = "```text target-capabilities-matrix"
OBSOLETE_BRACKET_START = "[target-capabilities:start]"
OBSOLETE_BRACKET_END = "[target-capabilities:end]"


def _load_module():
    return check_target_capabilities


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _valid_doc_body(matrix: str = "Target | OS\n------ | --") -> str:
    return (
        f"# Supported targets\n\n## Capability matrix\n\n{START_MARKER}\n{matrix}\n{END_MARKER}\n"
    )


def test_current_valid_document_passes_check() -> None:
    result = _run_script("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_duplicate_start_marker_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "SUPPORTED_APPS.md"
    doc.write_text(_valid_doc_body() + f"\n{START_MARKER}\n", encoding="utf-8")
    module = _load_module()

    monkeypatch.setattr(module, "SUPPORTED_DOC", doc)
    errors = module.marker_structure_errors(doc.read_text(encoding="utf-8"))
    assert any("start marker" in err for err in errors)


def test_duplicate_end_marker_detected() -> None:
    module = _load_module()

    text = _valid_doc_body() + f"\n{END_MARKER}\n"
    errors = module.marker_structure_errors(text)
    assert any("end marker" in err for err in errors)


def test_duplicate_full_block_detected() -> None:
    module = _load_module()

    text = _valid_doc_body() + "\n" + _valid_doc_body("Other | row")
    errors = module.marker_structure_errors(text)
    assert any("start marker" in err for err in errors)


def test_missing_start_marker_detected() -> None:
    module = _load_module()

    text = f"{END_MARKER}\nTarget | OS\n"
    errors = module.marker_structure_errors(text)
    assert any("start marker" in err for err in errors)


def test_missing_end_marker_detected() -> None:
    module = _load_module()

    text = f"{START_MARKER}\nTarget | OS\n"
    errors = module.marker_structure_errors(text)
    assert any("end marker" in err for err in errors)


def test_end_before_start_detected() -> None:
    module = _load_module()

    text = f"{END_MARKER}\nTarget | OS\n{START_MARKER}\n"
    errors = module.marker_structure_errors(text)
    assert any("after start" in err for err in errors)


def test_stale_generated_content_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "SUPPORTED_APPS.md"
    doc.write_text(_valid_doc_body("Stale | content"), encoding="utf-8")
    module = _load_module()

    monkeypatch.setattr(module, "SUPPORTED_DOC", doc)
    data = json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))
    errors = module._check_supported_doc(data)
    assert any("stale" in err for err in errors)


def test_obsolete_marker_rejected() -> None:
    module = _load_module()

    text = _valid_doc_body() + f"\n{OBSOLETE_MATRIX_MARKER}\n"
    errors = module.marker_structure_errors(text)
    assert any("obsolete" in err for err in errors)

    bracket = (
        "# Supported targets\n\n## Capability matrix\n\n"
        "[target-capabilities:start]\nTarget | OS\n------ | --\n"
        "[target-capabilities:end]\n"
    )
    errors = module.marker_structure_errors(bracket)
    assert any("obsolete" in err and "bracket" in err for err in errors)


def test_write_twice_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "SUPPORTED_APPS.md"
    doc.write_text(
        ROOT.joinpath("docs/SUPPORTED_APPS.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    bundled = tmp_path / "target-validation.json"
    module = _load_module()

    monkeypatch.setattr(module, "SUPPORTED_DOC", doc)
    monkeypatch.setattr(module, "BUNDLED_VALIDATION_FILE", bundled)
    data = json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))
    matrix = module._render_matrix(data)
    module._write_supported_doc(matrix)
    module._write_bundled_validation(data)
    first_doc = doc.read_bytes()
    first_bundled = bundled.read_bytes()
    module._write_supported_doc(matrix)
    module._write_bundled_validation(data)
    assert doc.read_bytes() == first_doc
    assert bundled.read_bytes() == first_bundled


def test_write_with_malformed_markers_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "SUPPORTED_APPS.md"
    doc.write_text("# doc\n", encoding="utf-8")
    module = _load_module()

    monkeypatch.setattr(module, "SUPPORTED_DOC", doc)
    data = json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit):
        module._write_supported_doc(module._render_matrix(data))
