"""The emulator's gate-averager self-check (hil/emulator/ga_selfcheck.c): its reference hash is the host build's."""
import ctypes as C
import re
import tempfile
from pathlib import Path

from sil_fixtures import run_in_child

from srmsil.build import compile_host

ROOT = Path(__file__).parents[2]
EMU = ROOT / "hil" / "emulator"
PLANT = ROOT / "src" / "srmsil" / "c" / "plant"
SHIM = Path(__file__).parent / "c" / "ga_selfcheck_shim.c"
CACHE = Path(tempfile.gettempdir()) / "srm_hil_ga_selfcheck_tests"


def _hash(lib):
    dll = C.CDLL(str(lib))
    dll.shim_ga_selfcheck.restype = C.c_uint32
    return dll.shim_ga_selfcheck()


def test_reference_hash_is_the_host_build():
    lib = compile_host([SHIM, EMU / "ga_selfcheck.c", PLANT / "srm_gate_avg.c"], [EMU, PLANT], CACHE,
                       defines=("SRM_TABLE_FLOAT",))
    ref = int(re.search(r"#define EMU_GA_SELFCHECK_HASH 0x([0-9a-fA-F]{8})u", (EMU / "ga_selfcheck.h").read_text())
              .group(1), 16)
    assert run_in_child(_hash, lib) == ref
