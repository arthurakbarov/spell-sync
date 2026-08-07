"""Environment contract SSOT: Python pin, uv policy, and committed declarations."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts.environment_contract.contract import CANONICAL_PYTHON, load_contract

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "environment-contract.toml"
PYTHON_VERSION_PATH = ROOT / ".python-version"
PYPROJECT_PATH = ROOT / "pyproject.toml"


def _read_toml(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_python_version_file_matches_contract() -> None:
    contract = load_contract(ROOT)
    assert PYTHON_VERSION_PATH.is_file(), "[ENVIRONMENT-PYTHON-002] missing .python-version"
    assert PYTHON_VERSION_PATH.read_text(encoding="utf-8").strip() == contract.canonical_python
    assert contract.canonical_python == CANONICAL_PYTHON


def test_environment_contract_declares_product_python_requirement() -> None:
    assert CONTRACT_PATH.is_file(), "[ENVIRONMENT-CONTRACT-001] missing environment contract"
    data = _read_toml(CONTRACT_PATH)
    assert int(data.get("schemaVersion", 0)) == 1
    product = data.get("product", {})
    assert isinstance(product, dict)
    requirement = str(product.get("pythonRequirement", ""))
    assert requirement == ">=3.14,<3.15"


def test_pyproject_requires_python_matches_contract() -> None:
    contract = load_contract(ROOT)
    pyproject = _read_toml(PYPROJECT_PATH)
    project = pyproject.get("project", {})
    assert isinstance(project, dict)
    requires_python = str(project.get("requires-python", ""))
    assert requires_python == contract.product_python_requirement
    assert requires_python == ">=3.14,<3.15"


def test_uv_required_version_pinned_in_pyproject_and_contract() -> None:
    contract = load_contract(ROOT)
    pyproject = _read_toml(PYPROJECT_PATH)
    tool = pyproject.get("tool", {})
    uv_config = tool.get("uv", {}) if isinstance(tool, dict) else {}
    assert isinstance(uv_config, dict)
    required_version = str(uv_config.get("required-version", ""))
    assert required_version == f"=={contract.uv_required_version}"
    assert contract.uv_required_version == "0.11.21"


def test_validate_environment_contract_script_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_environment_contract.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "ENVIRONMENT_CONTRACT_VALIDATION=success" in output


@pytest.mark.parametrize(
    "marker",
    [
        "[ENVIRONMENT-CONTRACT-001]",
        "[ENVIRONMENT-PYTHON-002]",
        "[ENVIRONMENT-UV-003]",
        "[ENVIRONMENT-LOCK-004]",
        "[ENVIRONMENT-VENV-005]",
    ],
)
def test_validate_environment_contract_uses_stable_error_ids(marker: str) -> None:
    text = (ROOT / "scripts" / "validate_environment_contract.py").read_text(encoding="utf-8")
    assert marker in text
