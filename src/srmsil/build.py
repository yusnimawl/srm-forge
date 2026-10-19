"""C compiler driver for controller folders: host shared library and target check."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HOST_FLAGS = ["-shared", "-O2", "-std=c99", "-Wall", "-Wextra", "-fPIC", "-DSRM_SIM_BUILD"]
CHECK_FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
ARM_GCC = ["arm-none-eabi-gcc", "-mcpu=cortex-m7", "-mfpu=fpv5-d16", "-mfloat-abi=hard", "-mthumb"]
ZIG_TARGET = ["-target", "thumb-linux-musleabihf", "-mcpu=cortex_m7"]


class CompileError(Exception):
    def __init__(self, log: str):
        super().__init__(log)
        self.log = log


@dataclass(frozen=True)
class TargetCheck:
    ok: bool
    compiler: str
    log: str


def zig_cc() -> list[str]:
    return [sys.executable, "-m", "ziglang", "cc"]


def _zig_version() -> str:
    r = subprocess.run([sys.executable, "-m", "ziglang", "version"], capture_output=True, text=True)
    return r.stdout.strip()


def controller_sources(folder: Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"controller folder {folder} does not exist or is not a directory")
    sources = sorted(folder.glob("*.c"))
    if not sources:
        raise ValueError(f"controller folder {folder} holds no .c file")
    return sources


def _incs(include_dirs: list[Path]) -> list[str]:
    return [f"-I{d}" for d in include_dirs]


def _cache_key(sources: list[Path], include_dirs: list[Path]) -> str:
    h = hashlib.sha256()
    h.update(_zig_version().encode())
    h.update(" ".join(HOST_FLAGS).encode())
    for s in sources:
        h.update(Path(s).read_bytes())
    for d in include_dirs:
        for hdr in sorted(Path(d).glob("*.h")):
            h.update(hdr.read_bytes())
    return h.hexdigest()


def compile_host(sources: list[Path], include_dirs: list[Path], out_dir: Path, log: list[str] | None = None) -> Path:
    """Compile (or find in the cache) the host library. `log`, if given, receives the compiler output of a fresh build."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".dll" if os.name == "nt" else ".so"
    lib = out_dir / f"srmsil_{_cache_key(sources, include_dirs)[:32]}{suffix}"
    if lib.exists():
        return lib
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=out_dir)
    os.close(fd)
    try:
        r = subprocess.run(
            [*zig_cc(), *HOST_FLAGS, *_incs(include_dirs), "-o", tmp, *map(str, sources)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise CompileError(r.stderr + r.stdout)
        if log is not None:
            log.append(r.stderr + r.stdout)
        try:
            os.replace(tmp, lib)
        except PermissionError:
            if not lib.exists():  # another process holds the finished library open
                raise
    finally:
        Path(tmp).unlink(missing_ok=True)
        Path(tmp).with_suffix(".lib").unlink(missing_ok=True)
        Path(tmp).with_suffix(".pdb").unlink(missing_ok=True)
    return lib


def target_check(sources: list[Path], include_dirs: list[Path]) -> TargetCheck:
    if shutil.which("arm-none-eabi-gcc"):
        cc, name = ARM_GCC, "arm-none-eabi-gcc"
    else:
        cc, name = [*zig_cc(), *ZIG_TARGET], "zig cc thumb-linux-musleabihf"
    logs, ok = [], True
    with tempfile.TemporaryDirectory() as d:
        for i, s in enumerate(sources):
            r = subprocess.run(
                [*cc, *CHECK_FLAGS, *_incs(include_dirs), "-c", "-o", str(Path(d) / f"{i}.o"), str(s)],
                capture_output=True, text=True,
            )
            ok = ok and r.returncode == 0
            logs.append(r.stderr + r.stdout)
    return TargetCheck(ok, name, "".join(logs))
