"""Platform support checks and load checks that run before any benchmark work."""

from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil

RAM_MIN_GB = {"quick": 4, "standard": 4, "long": 8}
DISK_MIN_GB = 2
MIN_CPUS = 2
GLIBC_MIN = (2, 28)
WIN_BUILD_MIN = 17134

# Total RAM is reported below the installed figure (reserved memory), so a machine passes at this share.
RAM_ACCEPT_SHARE = 0.9
BUSY_CPU_PERCENT = 20.0

_SUPPORTED = "Windows 10 1803+ or 11 on x64, Linux x86_64 with glibc 2.28+."
_IMPORTS = ("srmcore", "gmsh", "ngsolve")


@dataclass(frozen=True)
class Platform:
    system: str
    machine: str
    libc: str
    glibc: tuple[int, int] | None
    windows_build: int | None
    ram_gb: float
    available_ram_gb: float
    free_disk_gb: float
    logical_cpus: int


@dataclass(frozen=True)
class Problem:
    fatal: bool
    message: str


def _libc() -> tuple[str, tuple[int, int] | None]:
    if platform.system() != "Linux":
        return "", None
    name, version = platform.libc_ver()
    if name == "glibc":
        parts = version.split(".")
        try:
            return "glibc", (int(parts[0]), int(parts[1]))
        except (IndexError, ValueError):
            return "glibc", None
    try:
        # musl's ldd prints its banner to stderr and exits non-zero.
        out = subprocess.run(["ldd", "--version"], capture_output=True, text=True, timeout=10)
        if "musl" in (out.stdout + out.stderr).lower():
            return "musl", None
    except (OSError, subprocess.SubprocessError):
        pass
    return "", None


def _free_disk_gb(path: Path) -> float:
    probe = path.resolve()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free / 1e9


def current_platform(runtime_dir: Path) -> Platform:
    libc, glibc = _libc()
    build = sys.getwindowsversion().build if platform.system() == "Windows" else None
    mem = psutil.virtual_memory()
    return Platform(
        system=platform.system(),
        machine=platform.machine(),
        libc=libc,
        glibc=glibc,
        windows_build=build,
        ram_gb=mem.total / 1e9,
        available_ram_gb=mem.available / 1e9,
        free_disk_gb=_free_disk_gb(runtime_dir),
        logical_cpus=psutil.cpu_count(logical=True) or 1,
    )


def _unsupported_reason(p: Platform) -> str | None:
    if p.system == "Windows":
        if p.machine != "AMD64":
            return f"Windows on {p.machine}"
        if p.windows_build is None or p.windows_build < WIN_BUILD_MIN:
            return f"Windows build {p.windows_build} is older than {WIN_BUILD_MIN}"
        return None
    if p.system == "Linux":
        if p.machine != "x86_64":
            return f"Linux on {p.machine}"
        if p.libc == "musl":
            return "musl libc"
        if p.glibc is None or p.glibc < GLIBC_MIN:
            have = ".".join(map(str, p.glibc)) if p.glibc else "unknown"
            return f"glibc {have} is older than {GLIBC_MIN[0]}.{GLIBC_MIN[1]}"
        return None
    return f"{p.system or 'unknown OS'} is not a supported OS"


def check_platform(p: Platform, tier: str | None) -> list[Problem]:
    problems: list[Problem] = []
    reason = _unsupported_reason(p)
    if reason:
        problems.append(Problem(True, f"This machine is not supported: {reason}. Supported: {_SUPPORTED}"))
    if tier is not None and p.ram_gb < RAM_ACCEPT_SHARE * RAM_MIN_GB[tier]:
        problems.append(Problem(True, f"{tier} needs at least {RAM_MIN_GB[tier]} GB RAM; this machine has {p.ram_gb:.1f} GB."))
    if p.free_disk_gb < DISK_MIN_GB:
        problems.append(Problem(True, f"Needs {DISK_MIN_GB} GB free disk for the benchmark environment; {p.free_disk_gb:.1f} GB free."))
    if p.logical_cpus < MIN_CPUS:
        problems.append(Problem(True, f"Needs at least {MIN_CPUS} logical CPUs; this machine has {p.logical_cpus}."))
    return problems


def check_imports() -> list[Problem]:
    problems = []
    for name in _IMPORTS:
        try:
            importlib.import_module(name)
        except Exception as exc:  # any import-time failure makes the environment unusable
            problems.append(Problem(True, f"Cannot import {name}: {type(exc).__name__}: {exc}"))
    return problems


def check_load(sample_s: float = 3.0) -> list[Problem]:
    problems = []
    battery = psutil.sensors_battery()
    if battery is not None and not battery.power_plugged:
        problems.append(Problem(False, "The machine is running on battery; plug it in for a representative timing."))
    busy = psutil.cpu_percent(interval=sample_s)
    if busy > BUSY_CPU_PERCENT:
        problems.append(Problem(False, f"The CPU is {busy:.0f}% busy with other work; close other programs for a representative timing."))
    return problems


def max_workers(logical: int, available_gb: float, per_worker_gb: float | None, cap: int | None) -> int:
    n = logical
    if cap is not None:
        n = min(n, cap)
    if per_worker_gb is not None:
        n = min(n, int((available_gb - 1) // per_worker_gb))
    return max(n, 1)
