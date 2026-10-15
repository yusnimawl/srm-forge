"""Machine description and package versions recorded in result files. Holds no user name, host name or address."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
from pathlib import Path

import psutil

_PACKAGES = ("srmcore", "numpy", "scipy", "gmsh", "ngsolve", "matplotlib", "psutil")


def _cpu_model() -> str:
    try:
        import cpuinfo

        brand = cpuinfo.get_cpu_info().get("brand_raw")
        if brand:
            return str(brand)
    except Exception:
        pass
    return platform.processor() or "unknown"


def _glibc() -> str | None:
    name, version = platform.libc_ver()
    return version if name == "glibc" and version else None


def machine_info() -> dict:
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "cpu_model": _cpu_model(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "python": platform.python_version(),
        "glibc": _glibc(),
    }


def package_versions() -> dict:
    out = {}
    for name in _PACKAGES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def git_commit(repo: Path, run=subprocess.run) -> str | None:
    """Short HEAD of the checkout the engine is installed from, plus "-dirty" when tracked files differ;
    None without git or on any error."""
    def git(*args: str) -> str:
        proc = run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   timeout=10)
        if proc.returncode != 0:
            raise OSError(proc.stderr)
        return proc.stdout.strip()

    try:
        commit = git("rev-parse", "--short", "HEAD")
        if not commit:
            return None
        return commit + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")
    except (OSError, subprocess.SubprocessError):
        return None


def lock_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
