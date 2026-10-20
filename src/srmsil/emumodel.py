"""PC build of the real-time emulator: float tables on the emulator grid, stepped from averaged gate edges."""

from __future__ import annotations

import ctypes as C
import math
import multiprocessing as mp
import tempfile
from pathlib import Path

import numpy as np

from srmsil import _abi
from srmsil.build import compile_host
from srmsil.run import SimError, SimSummary, make_config, summarise
from srmsil.scenario import Scenario
from srmsil.tables import MotorData, emu_tables

_C_DIR = Path(__file__).parent / "c"
EDGE_DTYPE = np.dtype([("t", "<u8"), ("gates", "<u2")], align=True)   # mirrors srm_edge_t


def edges_from_trace(traces: dict[str, np.ndarray], dt: float) -> np.ndarray:
    """One edge per change of the gate word in a SIL run's `gate_u`/`gate_l` traces (stride 1, step `dt`), tick = sample.
    The word before the first sample is all off."""
    t = traces["t"]
    if len(t) > 1 and not np.allclose(np.diff(t), dt, rtol=1e-6, atol=0):
        raise ValueError("the trace is decimated or has a different step than dt; run with a trace stride of 1")
    gu, gl = traces["gate_u"].astype(np.uint16), traces["gate_l"].astype(np.uint16)
    k = np.arange(gu.shape[0], dtype=np.uint16)[:, None]
    words = ((gu << k).sum(axis=0) | (gl << (8 + k)).sum(axis=0)).astype(np.uint16)
    idx = np.flatnonzero(np.diff(words.astype(np.int32), prepend=0) != 0)
    out = np.zeros(len(idx), EDGE_DTYPE)
    out["t"], out["gates"] = idx, words[idx]
    return out


def _library(cache_dir: Path) -> Path:
    plant = _C_DIR / "plant"
    return compile_host([*sorted(plant.glob("*.c")), _C_DIR / "emu" / "srm_emu.c"],
                        [_C_DIR, plant, _C_DIR / "sim"], Path(cache_dir) / "sil" / "build", defines=("SRM_TABLE_FLOAT",))


def _run_loaded(lib_path: Path, m: MotorData, edges: np.ndarray, scenario: Scenario, tick_s: float,
                grid: tuple[int, int]) -> SimSummary:
    lib = C.CDLL(str(Path(lib_path).resolve()))
    _abi.bind_tables(lib)
    lib.srm_emu_run.argtypes = [C.POINTER(_abi.Config), C.POINTER(_abi.Tables), C.c_void_p, C.c_int64, C.c_double,
                                C.POINTER(_abi.Summary)]
    lib.srm_emu_run.restype = C.c_int
    tab = emu_tables(m, *grid)
    cur, trq, wf = (np.ascontiguousarray(a, dtype=np.float32) for a in (tab.current, tab.torque, tab.w_field))
    ptr = lambda a: a.ctypes.data_as(C.POINTER(C.c_float))  # noqa: E731
    ctab = _abi.Tables(theta_step=tab.theta_step, psi_step=tab.psi_step, psi_max=tab.psi_max, i_max=tab.i_max,
                       n_theta=cur.shape[0], n_psi=cur.shape[1], current=C.cast(ptr(cur), C.POINTER(C.c_double)),
                       torque=C.cast(ptr(trq), C.POINTER(C.c_double)), w_field=C.cast(ptr(wf), C.POINTER(C.c_double)))
    cfg = make_config(m, scenario, (_abi.ParamStep * 1)(), 0, 1)
    edges = np.ascontiguousarray(edges, dtype=EDGE_DTYPE)
    csum = _abi.Summary()
    rc = lib.srm_emu_run(C.byref(cfg), C.byref(ctab), edges.ctypes.data, len(edges), tick_s, C.byref(csum))
    if rc != 0:
        raise ValueError(f"emulator model rejected the configuration (code {rc})")
    return summarise(csum, m.n_phases, scenario.n_steps, tab.roundtrip_error)


def _child_main(args: tuple, out: Path) -> None:
    import pickle
    try:
        out.write_bytes(pickle.dumps(("ok", _run_loaded(*args))))
    except Exception as e:  # noqa: BLE001 - relayed to the parent
        out.write_bytes(pickle.dumps(("err", f"{type(e).__name__}: {e}")))


def run_model(m: MotorData, edges: np.ndarray, scenario: Scenario, *, tick_s: float, step: float = 5e-6,
              grid: tuple[int, int] = (180, 192), cache_dir: Path, timeout_s: float = 300.0) -> SimSummary:
    """Run the emulator model for `scenario` (fixed speed, open loop) on the gate edges (ticks of `tick_s`), stepping
    at `step`, in a spawned child. The converter delays of the scenario are applied to the edges, in ticks."""
    import pickle
    if scenario.mode != "fixed":
        raise ValueError("the emulator model runs fixed-speed scenarios only (open loop, no dynamics)")
    ratio = step / tick_s
    if ratio < 1 or abs(ratio - round(ratio)) > 1e-6 * ratio:
        raise ValueError(f"emulator step {step} s is not a whole number of ticks of {tick_s} s")
    scn = scenario.model_copy(update={"dt": step})
    lib = _library(cache_dir)
    with tempfile.TemporaryDirectory(prefix="srmemu_") as tmp:
        out = Path(tmp) / "result.pkl"
        p = mp.get_context("spawn").Process(target=_child_main, args=((lib, m, edges, scn, tick_s, grid), out),
                                            daemon=True)
        p.start()
        p.join(timeout_s)
        if p.is_alive():
            p.kill()
            p.join()
            raise SimError(f"timed out after {timeout_s:g} s")
        if not out.exists():
            raise SimError(f"the emulator model crashed (exit code {p.exitcode})")
        kind, val = pickle.loads(out.read_bytes())
    if kind == "err":
        raise SimError(val)
    return val
