"""Environment path roots for production and hermetic tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EnvironmentPaths:
    home: Path
    state_root: Path
    cache_root: Path
    config_root: Path
    artifact_root: Path
    evidence_root: Path
    lightweight_receipt_root: Path
    snapshot_output: Path
    uv_cache_root: Path

    @property
    def ci_summary_path(self) -> Path:
        return self.artifact_root / "ci" / "ci-summary.json"

    @property
    def environment_evidence_path(self) -> Path:
        return self.artifact_root / "environment" / "environment.json"


def _default_state_root(home: Path) -> Path:
    raw = os.environ.get("XDG_STATE_HOME", "").strip()
    if raw:
        return Path(raw).expanduser().resolve() / "spell-sync" / "execution-control"
    return home / ".local" / "state" / "spell-sync" / "execution-control"


def production_environment_paths(root: Path) -> EnvironmentPaths:
    home = Path.home()
    artifact_root = root / ".artifacts"
    return EnvironmentPaths(
        home=home,
        state_root=_default_state_root(home),
        cache_root=Path(os.environ.get("XDG_CACHE_HOME", str(home / ".cache"))).expanduser()
        / "spell-sync",
        config_root=Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))).expanduser()
        / "spell-sync",
        artifact_root=artifact_root,
        evidence_root=artifact_root / "ci",
        lightweight_receipt_root=artifact_root / "lightweight-validation",
        snapshot_output=home / "code.zip",
        uv_cache_root=Path(
            os.environ.get("UV_CACHE_DIR", str(home / ".cache" / "uv"))
        ).expanduser(),
    )


def test_environment_paths(tmp_home: Path, *, project_root: Path) -> EnvironmentPaths:
    artifact_root = tmp_home / "artifacts"
    return EnvironmentPaths(
        home=tmp_home,
        state_root=tmp_home / "xdg-state" / "spell-sync" / "execution-control",
        cache_root=tmp_home / "xdg-cache" / "spell-sync",
        config_root=tmp_home / "xdg-config" / "spell-sync",
        artifact_root=artifact_root,
        evidence_root=artifact_root / "ci",
        lightweight_receipt_root=artifact_root / "lightweight-validation",
        snapshot_output=tmp_home / "snapshot" / "code.zip",
        uv_cache_root=tmp_home / "uv-cache",
    )
