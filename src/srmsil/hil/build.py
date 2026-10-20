"""Build and flash the two HIL firmwares with PlatformIO (installed by `hil/setup.bat` or `hil/setup.sh`)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from srmsil.hil import HilError
from srmsil.hil.config import HilModes, write_hil_config
from srmsil.run import REFERENCE, _CTRL_DIR, controller_dir
from srmsil.scenario import Scenario
from srmsil.tables import MotorData, ctrl_tables, write_header

HIL_DIR = Path(__file__).resolve().parents[3] / "hil"
RUNTIME = HIL_DIR / ".runtime"
PLANT_DIR = Path(__file__).resolve().parents[1] / "c" / "plant"
ENVS = ("emulator", "controller")
SETUP_MESSAGE = "PlatformIO is not set up; run hil/setup.bat (Windows) or hil/setup.sh"


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    log: str
    firmware_hash: int


def pio_executable() -> Path:
    exe = RUNTIME / ("Scripts/pio.exe" if os.name == "nt" else "bin/pio")
    if not exe.is_file():
        raise HilError(SETUP_MESSAGE)
    return exe


def _hash_files(h, files: list[Path]) -> None:
    for f in sorted(files):
        h.update(f.name.encode())
        h.update(f.read_bytes())


def _source_hash(ctrl_dirs: list[Path], gen_dir: Path, modes: HilModes) -> str:
    h = hashlib.sha256(modes.env_string.encode())
    hil_files = [p for p in HIL_DIR.rglob("*") if p.is_file() and ".runtime" not in p.parts and ".pio" not in p.parts]
    for folder in (*ctrl_dirs, PLANT_DIR, PLANT_DIR.parent, gen_dir):
        _hash_files(h, [p for p in Path(folder).glob("*") if p.suffix in (".c", ".h")])
    h.update(b"hil")
    for f in sorted(hil_files):
        h.update(str(f.relative_to(HIL_DIR)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def build_and_flash(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, *, cache_dir: Path,
                    upload: bool = True, log: list[str] | None = None) -> BuildResult:
    """Generate the case headers, compile both firmwares (and upload them when `upload`). A compile without upload
    of unchanged sources is served from a marker in the cache."""
    pio = pio_executable()
    cdir = controller_dir(controller)
    ctrl_dirs = [cdir, _CTRL_DIR / "common"] if controller in REFERENCE else [cdir]
    base = Path(cache_dir) / "sil" / "hil" / "build"
    stage = base / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    write_header(m, ctrl_tables(m), stage / "srm_motor_tables.h")
    write_hil_config(modes, scenario, m, stage / "hil_config.h")
    digest = _source_hash(ctrl_dirs, stage, modes)
    gen = base / digest[:16]
    gen.mkdir(parents=True, exist_ok=True)
    for name in ("srm_motor_tables.h", "hil_config.h"):
        (gen / name).write_bytes((stage / name).read_bytes())
    fw_hash = int(digest[:8], 16)
    marker = gen / "compiled.log"
    if not upload and marker.is_file():
        return BuildResult(True, marker.read_text(), fw_hash)
    env = {
        **os.environ,
        "PLATFORMIO_CORE_DIR": str(RUNTIME / "core"),
        "PLATFORMIO_BUILD_CACHE_DIR": str(RUNTIME / "build_cache"),
        "SRM_HIL_GEN_DIR": str(gen),
        "SRM_CTRL_DIR": os.pathsep.join(str(d) for d in ctrl_dirs),
        "SRM_HIL_MODES": modes.env_string,
        "SRM_HIL_FIRMWARE_HASH": f"{fw_hash:08x}",
    }
    cmd = [str(pio), "run", "-d", str(HIL_DIR), *(a for e in ENVS for a in ("-e", e))]
    if upload:
        cmd += ["-t", "upload"]
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise HilError(f"cannot run PlatformIO: {e}") from e
    out = r.stdout + r.stderr
    if log is not None:
        log.append(out)
    if r.returncode == 0 and not upload:
        marker.write_text(out)
    return BuildResult(r.returncode == 0, out, fw_hash)
