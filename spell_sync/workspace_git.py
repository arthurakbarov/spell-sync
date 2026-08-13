"""Optional Git helpers for a personal wordlist workspace (data-only repo)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import WORDLIST_FILENAME

_GIT_TIMEOUT_S = 30
_TRACKED_NAMES = frozenset({WORDLIST_FILENAME, "spell-sync.toml"})


@dataclass(frozen=True)
class WorkspaceGitStatus:
    """Git state for wordlist.txt / spell-sync.toml beside the word list."""

    repo_root: Path
    dirty_relpaths: tuple[str, ...]
    has_upstream: bool

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_relpaths)

    @property
    def dirty_names(self) -> tuple[str, ...]:
        return tuple(Path(path).name for path in self.dirty_relpaths)


def _git(
    repo: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=False,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_S,
    )


def git_available() -> bool:
    return shutil.which("git") is not None


def find_git_toplevel(start: Path) -> Path | None:
    """Return git toplevel containing ``start``, or None if not in a repo / no git."""
    if not git_available():
        return None
    probe = start if start.is_dir() else start.parent
    try:
        completed = _git(probe, "rev-parse", "--show-toplevel")
    except OSError, subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    if not root:
        return None
    return Path(root)


def resolve_git_hooks_dir(start: Path) -> Path | None:
    """Return the hooks directory Git would use for ``start``, if available."""
    repo = find_git_toplevel(start)
    if repo is None:
        return None
    try:
        completed = _git(repo, "rev-parse", "--git-path", "hooks")
    except OSError, subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    raw = completed.stdout.strip()
    if not raw:
        return None
    hooks = Path(raw)
    if not hooks.is_absolute():
        hooks = repo / hooks
    return hooks


def _tracked_pathspecs(repo: Path, project_dir: Path) -> tuple[str, ...] | None:
    """Pathspecs for personal files under ``project_dir`` relative to ``repo``."""
    try:
        rel = project_dir.resolve().relative_to(repo.resolve())
    except ValueError:
        return None
    specs: list[str] = []
    for name in sorted(_TRACKED_NAMES):
        specs.append(name if rel == Path(".") else (rel / name).as_posix())
    return tuple(specs)


def inspect_workspace_git(project_dir: Path) -> WorkspaceGitStatus | None:
    """Inspect dirty personal files when ``project_dir`` lives in a Git repo.

    Returns None when Git is unavailable or the folder is not a repository.
    """
    repo = find_git_toplevel(project_dir)
    if repo is None:
        return None
    specs = _tracked_pathspecs(repo, project_dir)
    if specs is None:
        return None
    try:
        completed = _git(repo, "status", "--porcelain", "--", *specs)
    except OSError, subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    project_resolved = project_dir.resolve()
    dirty: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[-1].strip().strip('"')
        name = Path(path).name
        if name not in _TRACKED_NAMES:
            continue
        full = (repo / path).resolve()
        try:
            full.relative_to(project_resolved)
        except ValueError:
            if full.parent != project_resolved:
                continue
        dirty.append(path.replace("\\", "/"))
    rank = {WORDLIST_FILENAME: 0, "spell-sync.toml": 1}
    dirty.sort(key=lambda item: (rank.get(Path(item).name, 9), item))
    has_upstream = False
    try:
        upstream = _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}")
        has_upstream = upstream.returncode == 0 and bool(upstream.stdout.strip())
    except OSError, subprocess.TimeoutExpired:
        has_upstream = False
    return WorkspaceGitStatus(
        repo_root=repo,
        dirty_relpaths=tuple(dirty),
        has_upstream=has_upstream,
    )


def workspace_git_dirty_message(status: WorkspaceGitStatus) -> str:
    files = ", ".join(status.dirty_names)
    push_hint = " --push" if status.has_upstream else ""
    return (
        f"Personal workspace Git has uncommitted changes ({files}). "
        f"Run: spell-sync git-save{push_hint}"
    )


def commit_personal_workspace(
    status: WorkspaceGitStatus,
    *,
    message: str,
) -> tuple[bool, str]:
    """Stage and commit only dirty personal files. Returns (ok, detail)."""
    if not status.is_dirty:
        return True, "nothing to commit"
    try:
        add = _git(status.repo_root, "add", "--", *status.dirty_relpaths)
        if add.returncode != 0:
            return False, (add.stderr or add.stdout or "git add failed").strip()
        # Pathspecs keep unrelated staged files out of this commit.
        commit = _git(
            status.repo_root,
            "commit",
            "-m",
            message,
            "--",
            *status.dirty_relpaths,
        )
        if commit.returncode != 0:
            return False, (commit.stderr or commit.stdout or "git commit failed").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return True, "committed"


def push_personal_workspace(status: WorkspaceGitStatus) -> tuple[bool, str]:
    """Push current branch to its upstream. Returns (ok, detail)."""
    if not status.has_upstream:
        return False, "no upstream branch configured (git push -u origin HEAD once)"
    try:
        push = _git(status.repo_root, "push")
        if push.returncode != 0:
            return False, (push.stderr or push.stdout or "git push failed").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return True, "pushed"
