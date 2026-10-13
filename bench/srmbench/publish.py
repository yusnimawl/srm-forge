"""Committing and pushing the result files and the README comparison with git."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

# Relative to the repository root; these are the only paths ever staged or committed.
PUBLISHED_PATHS = ("bench/results", "bench/README.md")
# Files the report generator writes; publish restores them before the pull and rebuilds them after it.
README_PATH = "bench/README.md"
CHARTS_DIR = "bench/results/charts"


def _git(run, repo: Path, *args: str):
    return run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _reason(proc) -> str:
    return (proc.stderr or proc.stdout or "").strip() or f"exit code {proc.returncode}"


class _Stop(Exception):
    """A publishing step failed; the message says which and why."""


def _step(run, repo: Path, name: str, *args: str):
    try:
        proc = _git(run, repo, *args)
    except OSError:
        raise _Stop("git not found on PATH") from None
    if proc.returncode != 0:
        raise _Stop(f"git {name} failed: {_reason(proc)}")
    return proc


def git_ready(repo: Path, run=subprocess.run) -> tuple[bool, str]:
    """(True, "") when git is on PATH, `repo` is inside a work tree and a remote exists; else (False, what is missing)."""
    try:
        inside = _git(run, repo, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return False, f"{repo} is not inside a git work tree"
        remotes = _git(run, repo, "remote")
    except OSError:
        return False, "git not found on PATH"
    if remotes.returncode != 0 or not remotes.stdout.strip():
        return False, "no git remote is configured"
    return True, ""


def _ahead(run, repo: Path) -> int:
    """Commits on HEAD that the upstream branch lacks; raises _Stop without an upstream."""
    try:
        up = _git(run, repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    except OSError:
        raise _Stop("git not found on PATH") from None
    if up.returncode != 0:
        raise _Stop("the current branch has no upstream branch (or HEAD is detached), so nothing was committed; "
                    "set the upstream, then run --report-only and commit the results by hand")
    count = _step(run, repo, "rev-list", "rev-list", "--count", "@{u}..HEAD")
    try:
        return int(count.stdout.strip())
    except ValueError:
        raise _Stop(f"git rev-list gave {count.stdout.strip()!r} instead of a commit count") from None


def _lines(proc) -> list[str]:
    return [x for x in proc.stdout.splitlines() if x.strip()]


def _restore_generated(run, repo: Path) -> None:
    """Put the README and the charts back to HEAD: tracked ones are checked out, untracked charts removed.
    They are rebuilt after the pull, and a modified or untracked copy would block or conflict with it."""
    tracked = _lines(_step(run, repo, "ls-files", "ls-files", "--", README_PATH, CHARTS_DIR))
    if tracked:
        _step(run, repo, "checkout", "checkout", "HEAD", "--", *tracked)
    for name in _lines(_step(run, repo, "ls-files", "ls-files", "--others", "--exclude-standard", "--", CHARTS_DIR)):
        (repo / name).unlink(missing_ok=True)


def publish(repo: Path, message: str, rebuild: Callable[[], None], run=subprocess.run) -> tuple[bool, str]:
    """Commit the new results and push them, touching nothing but `PUBLISHED_PATHS`.

    Nothing is done unless the branch has an upstream and no unpushed commits, because `git push` would send
    them too; after the commit, the push happens only when that commit is the single one ahead. The README and
    charts are restored to HEAD, then `git pull --rebase` runs (it refuses on any other tracked change), then
    `rebuild()` regenerates them. Stops at the first failing step and returns (False, which step and why); the
    result files stay in place."""
    try:
        n = _ahead(run, repo)
        if n:
            return False, (f"your branch has {n} unpushed commit{'s' if n != 1 else ''}; push them yourself, "
                           "then run --report-only and commit the results by hand")
        _restore_generated(run, repo)
        _step(run, repo, "pull", "pull", "--rebase")
        try:
            rebuild()
        except Exception as exc:  # the README rebuild is caller code; report it like a failed step
            raise _Stop(f"rebuilding the README failed: {type(exc).__name__}: {exc}") from None
        _step(run, repo, "add", "add", *PUBLISHED_PATHS)
        _step(run, repo, "commit", "commit", "-m", message, "--", *PUBLISHED_PATHS)
        n = _ahead(run, repo)
        if n != 1:
            return False, (f"after the commit the branch is {n} commits ahead of its upstream instead of 1, "
                           "so nothing was pushed; check `git log @{u}..HEAD` and push by hand")
        _step(run, repo, "push", "push")
    except _Stop as stop:
        return False, str(stop)
    return True, "Committed and pushed."
