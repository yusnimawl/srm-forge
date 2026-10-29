"""Build and flash the two HIL firmwares with PlatformIO (installed by `hil/setup.bat` or `hil/setup.sh`)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from srmsil.hil import HilError
from srmsil.hil.config import HilModes, mode_defines, write_hil_config
from srmsil.run import REFERENCE, _CTRL_DIR, controller_dir
from srmsil.scenario import Scenario
from srmsil.tables import MotorData, ctrl_tables, write_header

HIL_DIR = Path(__file__).resolve().parents[3] / "hil"
RUNTIME = HIL_DIR / ".runtime"
PLANT_DIR = Path(__file__).resolve().parents[1] / "c" / "plant"
TIMEOUT_S = 900
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
    hil_files = []
    for root, dirs, files in os.walk(HIL_DIR):
        dirs[:] = [d for d in dirs if d not in (".runtime", ".pio")]
        hil_files += [Path(root) / f for f in files]
    for folder in (*ctrl_dirs, PLANT_DIR, PLANT_DIR.parent, gen_dir):
        _hash_files(h, [p for p in Path(folder).glob("*") if p.suffix in (".c", ".h")])
    h.update(b"hil")
    for f in sorted(hil_files):
        h.update(str(f.relative_to(HIL_DIR)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _stage(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, stage: Path) -> tuple[list[Path], str]:
    """Write the case headers into `stage`; the controller's source folders and the digest of the whole build."""
    cdir = controller_dir(controller)
    ctrl_dirs = [cdir, _CTRL_DIR / "common"] if controller in REFERENCE else [cdir]
    stage.mkdir(parents=True, exist_ok=True)
    write_header(m, ctrl_tables(m), stage / "srm_motor_tables.h")
    write_hil_config(modes, scenario, m, stage / "hil_config.h")
    return ctrl_dirs, _source_hash(ctrl_dirs, stage, modes)


def firmware_hash(controller: str, m: MotorData, scenario: Scenario, modes: HilModes) -> int:
    """The firmware hash build_and_flash gives (controller, case, scenario, modes) from the sources as they are now:
    the controller folder(s), the plant and HIL sources and the generated headers. Nothing is compiled."""
    with tempfile.TemporaryDirectory(prefix="srm_hil_hash_") as tmp:
        return int(_stage(controller, m, scenario, modes, Path(tmp))[1][:8], 16)


def check_sources(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, flashed: int,
                  boards: HilModes | None = None) -> None:
    """Raise HilError when the build of (controller, case, scenario, modes) from the current sources is not the one
    flashed (`flashed`, its firmware hash): the controller folder, the case's tables or the scenario's build settings
    changed since the last Build & Flash. With `boards` (the modes the boards report) a requested `modes` that
    differs is named first, since the hash would differ for that reason alone."""
    if boards is not None and mode_defines(boards) != mode_defines(modes):
        raise HilError(f"the requested modes {modes.env_string} differ from the modes the boards were flashed with "
                       f"({boards.env_string}); choose the flashed modes or build and flash again")
    now = firmware_hash(controller, m, scenario, modes)
    if now != flashed:
        raise HilError(f"the controller sources changed since the last Build & Flash (the build is now {now:08x}, the "
                       f"boards run {flashed:08x}: the controller folder, the case's tables or the scenario's build "
                       "settings differ); build and flash again")


def build_and_flash(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, *, cache_dir: Path,
                    upload: bool = True, log: list[str] | None = None) -> BuildResult:
    """Generate the case headers, compile both firmwares (and upload them when `upload`). A compile without upload
    of unchanged sources is served from a marker in the cache."""
    pio = pio_executable()
    base = Path(cache_dir).resolve() / "sil" / "hil" / "build"  # pio runs in hil/, so relative paths would miss
    stage = base / "stage"
    ctrl_dirs, digest = _stage(controller, m, scenario, modes, stage)
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
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or b"") if isinstance(e.stdout, bytes) else (e.stdout or "")
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        raise HilError(f"PlatformIO did not finish in {TIMEOUT_S} s (is a board attached?)" + "\n" + partial[-2000:]) from e
    except OSError as e:
        raise HilError(f"cannot run PlatformIO: {e}") from e
    out = r.stdout + r.stderr
    if log is not None:
        log.append(out)
    if r.returncode == 0 and not upload:
        marker.write_text(out)
    return BuildResult(r.returncode == 0, out, fw_hash)
