"""Committing and pushing the result files and the README comparison with git."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

# Relative to the repository root; these are the only paths ever staged or committed.
PUBLISHED_PATHS = ("bench/results", "bench/README.md")


def _git(run, repo: Path, *args: str):
    return run(["git", *args], cwd=repo, capture_output=True, text=True)


def _reason(proc) -> str:
    return (proc.stderr or proc.stdout or "").strip() or f"exit code {proc.returncode}"


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


def publish(repo: Path, message: str, rebuild: Callable[[], None], run=subprocess.run) -> tuple[bool, str]:
    """Pull, rebuild the README, then commit only the published paths and push. Stops at the first failing step
    and returns (False, which step failed and why); a failure leaves the result files in place."""
    steps = (
        ("pull", ("pull", "--rebase", "--autostash")),
        ("add", ("add", *PUBLISHED_PATHS)),
        ("commit", ("commit", "-m", message, "--", *PUBLISHED_PATHS)),
        ("push", ("push",)),
    )
    for name, args in steps:
        if name == "add":
            try:
                rebuild()
            except Exception as exc:  # the README rebuild is caller code; report it like a failed step
                return False, f"rebuilding the README failed: {type(exc).__name__}: {exc}"
        try:
            proc = _git(run, repo, *args)
        except OSError:
            return False, "git not found on PATH"
        if proc.returncode != 0:
            return False, f"git {name} failed: {_reason(proc)}"
    return True, "Committed and pushed."
