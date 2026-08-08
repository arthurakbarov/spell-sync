"""Structured interpreter probe executed inside the project .venv."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .manifest import DistributionRecord, InstalledManifest, manifest_digest

_PROBE_SCRIPT = """
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

project_root = Path(sys.argv[1])
purelib = Path(__import__("sysconfig").get_paths()["purelib"]).resolve()


def _in_venv(dist_info_path):
    try:
        return Path(dist_info_path).resolve().is_relative_to(purelib)
    except (OSError, ValueError):
        return False


def _identity(kind: str) -> str:
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    payload = "|".join(
        (
            kind,
            platform.python_implementation().lower(),
            platform.python_version(),
            sys.implementation.cache_tag or "",
            "isolated" if base_prefix != sys.prefix else "embedded",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


records = []
for dist in importlib.metadata.distributions():
    dist_path = getattr(dist, "_path", None)
    if dist_path is None or not _in_venv(dist_path):
        continue
    name = dist.metadata.get("Name")
    version = dist.version
    if not name or not version:
        continue
    normalized_name = name.lower().replace("_", "-")
    direct_url = dist.read_text("direct_url.json")
    editable = False
    source_type = "index"
    if direct_url:
        payload = json.loads(direct_url)
        url = payload.get("url", "")
        if isinstance(url, str) and url.startswith("file:"):
            source_type = "local-project"
            try:
                editable = Path(url.removeprefix("file:")).resolve() == project_root.resolve()
            except OSError:
                editable = False
        else:
            source_type = "direct-url"
    records.append(
        {
            "name": normalized_name,
            "version": version,
            "editable": editable,
            "sourceType": source_type,
        }
    )
records.sort(key=lambda item: item["name"])

pytest_version = ""
try:
    import pytest
except ImportError:
    pytest_version = ""
else:
    pytest_version = getattr(pytest, "__version__", "")

print(
    json.dumps(
        {
            "pythonImplementation": platform.python_implementation().lower(),
            "pythonVersion": platform.python_version(),
            "pythonCacheTag": sys.implementation.cache_tag or "",
            "executableIdentity": _identity("executable"),
            "basePrefixIdentity": _identity("base"),
            "pytestVersion": pytest_version,
            "installedManifest": {"schemaVersion": 1, "distributions": records},
        },
        sort_keys=True,
    )
)
"""


@dataclass(frozen=True, slots=True)
class InterpreterProbe:
    python_implementation: str
    python_version: str
    python_cache_tag: str
    executable_identity: str
    base_prefix_identity: str
    pytest_version: str
    installed_manifest: InstalledManifest

    @property
    def installed_environment_digest(self) -> str:
        return manifest_digest(self.installed_manifest)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "pythonImplementation": self.python_implementation,
            "pythonVersion": self.python_version,
            "pythonCacheTag": self.python_cache_tag,
            "executableIdentity": self.executable_identity,
            "basePrefixIdentity": self.base_prefix_identity,
            "pytestVersion": self.pytest_version,
            "installedManifest": self.installed_manifest.to_json_dict(),
        }


def venv_python(venv_dir: Path) -> Path | None:
    for name in ("python", "python3", "python3.14"):
        candidate = venv_dir / "bin" / name
        if candidate.is_file():
            return candidate
    candidate = venv_dir / "Scripts" / "python.exe"
    if candidate.is_file():
        return candidate
    return None


def run_interpreter_probe(python: Path, *, project_root: Path) -> InterpreterProbe:
    proc = subprocess.run(
        [str(python), "-c", _PROBE_SCRIPT, str(project_root)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("environment.probe-failed")
    payload = json.loads(proc.stdout)
    manifest_payload = payload.get("installedManifest", {})
    distributions = tuple(
        DistributionRecord(
            name=str(item["name"]),
            version=str(item["version"]),
            editable=bool(item["editable"]),
            source_type=str(item["sourceType"]),
        )
        for item in manifest_payload.get("distributions", [])
        if isinstance(item, dict)
    )
    return InterpreterProbe(
        python_implementation=str(payload.get("pythonImplementation", "")),
        python_version=str(payload.get("pythonVersion", "")),
        python_cache_tag=str(payload.get("pythonCacheTag", "")),
        executable_identity=str(payload.get("executableIdentity", "")),
        base_prefix_identity=str(payload.get("basePrefixIdentity", "")),
        pytest_version=str(payload.get("pytestVersion", "")),
        installed_manifest=InstalledManifest(schema_version=1, distributions=distributions),
    )
