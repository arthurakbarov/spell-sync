"""Normalized installed distribution manifest and digest."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DistributionRecord:
    name: str
    version: str
    editable: bool
    source_type: str


@dataclass(frozen=True, slots=True)
class InstalledManifest:
    schema_version: int
    distributions: tuple[DistributionRecord, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "distributions": [
                {
                    "name": item.name,
                    "version": item.version,
                    "editable": item.editable,
                    "sourceType": item.source_type,
                }
                for item in self.distributions
            ],
        }


def _source_type(dist: importlib.metadata.Distribution) -> str:
    direct_url = dist.read_text("direct_url.json")
    if direct_url:
        payload = json.loads(direct_url)
        url = payload.get("url", "")
        if isinstance(url, str) and url.startswith("file:"):
            return "local-project"
        return "direct-url"
    return "index"


def _is_editable(dist: importlib.metadata.Distribution, project_root: Path) -> bool:
    direct_url = dist.read_text("direct_url.json")
    if not direct_url:
        return False
    payload = json.loads(direct_url)
    url = payload.get("url", "")
    if not isinstance(url, str) or not url.startswith("file:"):
        return False
    try:
        resolved = Path(url.removeprefix("file:")).resolve()
        return resolved == project_root.resolve()
    except OSError:
        return False


def build_installed_manifest(
    *, project_root: Path, python: Path | None = None
) -> InstalledManifest:
    if python is not None:
        return _build_installed_manifest_subprocess(python=python, project_root=project_root)
    records: list[DistributionRecord] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        version = dist.version
        if not name or not version:
            continue
        normalized_name = name.lower().replace("_", "-")
        records.append(
            DistributionRecord(
                name=normalized_name,
                version=version,
                editable=_is_editable(dist, project_root),
                source_type=_source_type(dist),
            )
        )
    records.sort(key=lambda item: item.name)
    return InstalledManifest(schema_version=1, distributions=tuple(records))


def manifest_digest(manifest: InstalledManifest) -> str:
    payload = json.dumps(manifest.to_json_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_python_cache_tag() -> str:
    return sys.implementation.cache_tag or ""


def _build_installed_manifest_subprocess(*, python: Path, project_root: Path) -> InstalledManifest:
    script = """
import json
import importlib.metadata
from pathlib import Path

project_root = Path(__import__("sys").argv[1])
records = []
for dist in importlib.metadata.distributions():
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
print(json.dumps({"schemaVersion": 1, "distributions": records}, sort_keys=True))
"""
    proc = subprocess.run(
        [str(python), "-c", script, str(project_root)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("environment.dependencies-mismatch")
    payload = json.loads(proc.stdout)
    distributions = tuple(
        DistributionRecord(
            name=str(item["name"]),
            version=str(item["version"]),
            editable=bool(item["editable"]),
            source_type=str(item["sourceType"]),
        )
        for item in payload.get("distributions", [])
        if isinstance(item, dict)
    )
    return InstalledManifest(schema_version=1, distributions=distributions)
