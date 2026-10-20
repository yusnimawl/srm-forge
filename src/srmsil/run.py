"""Running a compiled controller against the simulator core."""

from __future__ import annotations

import ctypes as C
import json
import math
import multiprocessing as mp
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from srmsil import _abi
from srmsil.build import CompileError, compile_host, controller_sources
from srmsil.scenario import Scenario
from srmsil.tables import MotorData, ctrl_tables, sim_tables, write_header

TRACE_CAP = 2_000_000
ADC_HEADROOM = 1.25

_C_DIR = Path(__file__).parent / "c"
_SIM_DIR = _C_DIR / "sim"
_PLANT_DIR = _C_DIR / "plant"
_CTRL_DIR = _C_DIR / "controllers"
REFERENCE = {"hysteresis", "pwm_current", "tsf"}


class SimError(Exception):
    def __init__(self, log: str):
        super().__init__(log)
        self.log = log


class SimCancelled(SimError):
    """The caller's cancel callback fired while the child was running."""


@dataclass(frozen=True)
class SimSummary:
    mean_torque: float
    ripple_pct: float
    i_rms: np.ndarray
    copper_loss: float
    power_in: float
    power_mech: float
    beyond_map_fraction: float
    energy_error: float
    roundtrip_error: float


@dataclass(frozen=True)
class SimResult:
    traces: dict[str, np.ndarray]
    summary: SimSummary
    scenario: Scenario
    controller: str
    source_hash: str
    compile_log: str


def controller_dir(controller: str) -> Path:
    """Folder of a reference controller by name, else the given folder (checked for `.c` files)."""
    if controller in REFERENCE:
        return _CTRL_DIR / controller
    controller_sources(Path(controller))
    return Path(controller)


def sim_library(controller_dir: Path, header_dir: Path, cache_dir: Path, common_dir: Path | None = None,
                log: list[str] | None = None) -> Path:
    """Compile the simulator core and the controller folder (plus `common_dir`, if given) into a cached library."""
    folders = [Path(controller_dir), *([Path(common_dir)] if common_dir else [])]
    sources = [*sorted(_PLANT_DIR.glob("*.c")), *sorted(_SIM_DIR.glob("*.c")), *(s for f in folders for s in controller_sources(f))]
    return compile_host(sources, [_C_DIR, _PLANT_DIR, _SIM_DIR, Path(header_dir), *folders], Path(cache_dir) / "sil" / "build", log)


def _ptr(a: np.ndarray, ctype):
    return a.ctypes.data_as(C.POINTER(ctype))


def summarise(csum: _abi.Summary, n_phases: int, n_steps: int, roundtrip_error: float) -> SimSummary:
    """SimSummary of a finished run over its window (the second half of the steps)."""
    ws = max(csum.window_steps, 1)
    mean_t = csum.torque_sum / ws
    ripple = 100 * (csum.torque_max - csum.torque_min) / abs(mean_t) if abs(mean_t) > 1e-12 else math.nan
    e_in = csum.energy_in
    err = abs(e_in - csum.energy_mech - csum.energy_copper - (csum.w_field_end - csum.w_field_start)) / max(abs(e_in), 1e-12)
    return SimSummary(
        mean_torque=mean_t, ripple_pct=ripple, i_rms=np.sqrt(np.array(csum.i2_sum[:n_phases]) / ws),
        copper_loss=csum.copper_sum / ws, power_in=csum.power_in_sum / ws, power_mech=csum.power_mech_sum / ws,
        beyond_map_fraction=csum.beyond_map_steps / n_steps, energy_error=err, roundtrip_error=roundtrip_error)


def make_config(m: MotorData, scenario: Scenario, cps, n_param_steps: int, stride: int) -> _abi.Config:
    """The simulator Config of a scenario; `cps` is the ctypes ParamStep array."""
    q = m.n_phases
    n_steps = scenario.n_steps
    rpm = 2 * math.pi / 60
    cv = scenario.command_value * (rpm if scenario.command_mode == "speed" else 1.0)
    sc, se, ad = scenario.converter, scenario.sensors, scenario.adc
    full_scale = ad.full_scale or ADC_HEADROOM * float(m.currents[-1])
    cfg = _abi.Config(
        resistance=m.resistance, bus_voltage=scenario.bus_voltage or m.bus_voltage, dt=scenario.dt,
        speed=scenario.speed_rpm * rpm, theta0=scenario.theta0, inertia=scenario.inertia,
        friction=scenario.friction, load=scenario.load, load_step=scenario.load_step,
        load_step_time=scenario.load_step_time, pwm_hz=scenario.pwm_hz, isr_hz=scenario.resolved_isr_hz,
        compute_delay=scenario.resolved_compute_delay, command_value=cv, v_switch=sc.v_switch, v_diode=sc.v_diode,
        dead_time=sc.dead_time, turn_on_delay=sc.turn_on_delay, turn_off_delay=sc.turn_off_delay,
        adc_amps_per_count=full_scale / (2**ad.bits - 1),
        encoder_offset=se.encoder_offset, encoder_ecc_amp=se.encoder_ecc_amp,
        resolver_gain_mismatch=se.resolver_gain_mismatch, resolver_phase_error=se.resolver_phase_error,
        adc_offset_error=ad.offset_error, adc_gain_error=ad.gain_error, adc_noise=ad.noise, adc_rc_tau=ad.rc_tau,
        n_steps=n_steps, trace_stride=stride, n_phases=q, n_rotor_poles=m.n_rotor_poles,
        mode=int(scenario.mode == "dynamic"), command_mode=int(scenario.command_mode == "speed"),
        encoder_cpr=se.encoder_cpr, adc_bits=ad.bits, adc_offset_counts=ad.offset_counts, seed=scenario.seed,
        encoder_ecc_harmonic=se.encoder_ecc_harmonic, resolver=int(se.resolver),
        resolver_pole_pairs=se.resolver_pole_pairs, resolver_bits=se.resolver_bits, sensor_delay=se.delay,
        volt_full_scale=ad.volt_full_scale or 0.0, volt_rc_tau=ad.volt_rc_tau, param_steps=cps,
        n_param_steps=n_param_steps)
    return cfg


def _run_loaded(lib_path: Path, m: MotorData, scenario: Scenario) -> SimResult:
    """Load the library and run it. Call only in a child process: the library holds controller code and C state."""
    lib = C.CDLL(str(Path(lib_path).resolve()))
    _abi.bind(lib)
    cps = (_abi.ParamStep * max(len(scenario.param_steps), 1))()
    steps = sorted(scenario.param_steps, key=lambda s: s.time)   # stable: steps at one time keep list order
    for c, s in zip(cps, steps):
        c.t, c.value, c.name = s.time, s.value, s.name.encode()
    for name, value in scenario.params.items():
        if lib.srm_sim_param(name.encode(), value) != 0:
            raise ValueError(f"controller rejected parameter {name!r}")
    tab = sim_tables(m)
    q = m.n_phases
    n_steps = scenario.n_steps
    stride = math.ceil(n_steps / TRACE_CAP)
    n = math.ceil(n_steps / stride)
    cfg = make_config(m, scenario, cps, len(steps), stride)
    cur, trq, wf = (np.ascontiguousarray(a, dtype=np.float64) for a in (tab.current, tab.torque, tab.w_field))
    ctab = _abi.Tables(theta_step=tab.theta_step, psi_step=tab.psi_step, psi_max=tab.psi_max, i_max=tab.i_max,
                       n_theta=cur.shape[0], n_psi=cur.shape[1], current=_ptr(cur, C.c_double),
                       torque=_ptr(trq, C.c_double), w_field=_ptr(wf, C.c_double))
    scalars = {k: np.zeros(n) for k in ("t", "theta", "omega", "torque", "encoder", "resolver_sin", "resolver_cos")}
    phased = {k: np.zeros((q, n), np.float32) for k in ("i", "psi", "v", "adc_i", "adc_v")}
    gates = {k: np.zeros((q, n), np.uint8) for k in ("gate_u", "gate_l")}
    ctrace = _abi.Trace(n_samples=n)
    for k, a in scalars.items():
        setattr(ctrace, k, _ptr(a, C.c_double))
    for k, a in phased.items():
        setattr(ctrace, k, _ptr(a, C.c_float))
    for k, a in gates.items():
        setattr(ctrace, k, _ptr(a, C.c_uint8))
    csum = _abi.Summary()
    rc = lib.srm_sim_run(C.byref(cfg), C.byref(ctab), C.byref(ctrace), C.byref(csum))
    if rc == -3:
        raise ValueError(f"controller refused live parameter {steps[csum.refused - 1].name} (code {csum.refused_code})")
    if rc == -2:
        raise RuntimeError("the controller queued more gate commands than the simulator can delay; "
                           "shorten compute_delay or issue fewer commands")
    if rc != 0:
        raise RuntimeError(f"simulator rejected the configuration (code {rc})")
    got = ctrace.n_samples
    traces = {k: a[:got] for k, a in scalars.items()}
    traces.update({k: a[:, :got] for k, a in {**phased, **gates}.items()})
    summary = summarise(csum, q, n_steps, tab.roundtrip_error)
    return SimResult(traces, summary, scenario, "", "", "")


def _child_main(lib_path: Path, m: MotorData, scenario: Scenario, out: Path) -> None:
    try:
        save(_run_loaded(lib_path, m, scenario), out)
    except Exception as e:  # noqa: BLE001 - relayed to the parent as the run's error text
        if isinstance(e, OSError) and "access violation" in str(e):  # ctypes' report of a controller fault
            raise
        out.with_suffix(".err").write_text(str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}")


def run(m: MotorData, controller: str, scenario: Scenario, *, cache_dir: Path, timeout_s: float = 300.0,
        on_compiled: Callable[[], None] | None = None, cancel: Callable[[], bool] | None = None) -> SimResult:
    """Compile the controller and run the scenario in a spawned child, so controller faults cannot reach this process.

    `on_compiled` is called once the library is built, before the child starts. `cancel` is polled while the child
    runs; when it returns True the child is killed and `SimCancelled` is raised."""
    cdir = controller_dir(controller)
    common = _CTRL_DIR / "common" if controller in REFERENCE else None
    log: list[str] = []
    with tempfile.TemporaryDirectory(prefix="srmsil_") as tmp:
        hdr = Path(tmp)
        write_header(m, ctrl_tables(m), hdr / "srm_motor_tables.h")
        try:
            lib = sim_library(cdir, hdr, cache_dir, common, log)
        except CompileError as e:
            raise SimError(e.log) from e
        if on_compiled:
            on_compiled()
        out = hdr / "result.npz"
        p = mp.get_context("spawn").Process(target=_child_main, args=(lib, m, scenario, out), daemon=True)
        p.start()
        try:
            deadline = time.monotonic() + timeout_s
            while p.is_alive() and time.monotonic() < deadline:
                p.join(0.2)
                if cancel and cancel():
                    raise SimCancelled("cancelled")
            timed_out = p.is_alive()
        finally:
            if p.is_alive():
                p.kill()
                p.join()
        if timed_out:
            raise SimError(f"timed out after {timeout_s:g} s")
        err = out.with_suffix(".err")
        if err.exists():
            raise SimError(err.read_text())
        if not out.exists():
            raise SimError(f"the controller crashed (exit code {p.exitcode})")
        try:
            res = load(out)
        except OSError as e:
            raise SimError(f"could not read the child's result: {e}") from e
    return replace(res, controller=controller if controller in REFERENCE else str(cdir),
                   source_hash=lib.stem, compile_log="".join(log))


def save(result: SimResult, path: Path) -> None:
    """Write traces and the summary arrays to `path` (.npz) and the scenario, scalars and strings to a .json sidecar."""
    path = Path(path)
    s = result.summary
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, i_rms=s.i_rms, **{f"trace_{k}": (v.astype(np.float32) if k != "t" and v.dtype == np.float64 else v)
                                               for k, v in result.traces.items()})
    meta = {"scenario": result.scenario.model_dump(mode="json"), "controller": result.controller,
            "source_hash": result.source_hash, "compile_log": result.compile_log,
            "summary": {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                        for k, v in vars(s).items() if k != "i_rms"}}
    path.with_suffix(".json").write_text(json.dumps(meta, allow_nan=False))
    tmp.replace(path)


def load(path: Path) -> SimResult:
    path = Path(path)
    meta = json.loads(path.with_suffix(".json").read_text())
    with np.load(path) as z:
        traces = {k[6:]: z[k] for k in z.files if k.startswith("trace_")}
        summary = SimSummary(i_rms=z["i_rms"],
                              **{k: math.nan if v is None else v for k, v in meta["summary"].items()})
    return SimResult(traces, summary, Scenario.model_validate(meta["scenario"]), meta["controller"],
                     meta["source_hash"], meta["compile_log"])


def decimate(t: np.ndarray, y: np.ndarray, n_px: int) -> tuple[np.ndarray, np.ndarray]:
    """Min and max of y per equal-count bucket, in the order they occur, so plotted extremes survive."""
    if n_px < 1:
        raise ValueError("n_px must be at least 1")
    n = len(t)
    if n <= 2 * n_px:
        return t, y
    edges = np.linspace(0, n, n_px + 1).astype(int)
    idx = []
    for a, b in zip(edges[:-1], edges[1:]):
        lo, hi = a + int(np.argmin(y[a:b])), a + int(np.argmax(y[a:b]))
        idx.extend(sorted({lo, hi}))
    idx = np.array(idx)
    return t[idx], y[idx]


_SHARED_PARAMS = [
    ("theta_on", "electrical deg from unaligned", "0"),
    ("theta_off", "electrical deg from unaligned", "150"),
    ("speed_kp", "N*m/(rad/s)", "0.05"),
    ("speed_ki", "N*m/rad", "0.5"),
    ("speed_filter_hz", "Hz", "50"),
    ("torque_limit", "N*m", "SRM_T_MAX_NM"),
    ("resolver_pole_pairs", "-", "1"),
]

# Parameters each reference controller accepts (name, unit, default), as listed in its README.
PARAMS: dict[str, list[tuple[str, str, str]]] = {
    "hysteresis": [("band", "A", "0.05 * SRM_I_MAX_A"), ("soft", "1 = soft, 0 = hard", "1"), *_SHARED_PARAMS],
    "pwm_current": [("kp", "V/A", "0 (SRM_L_MIN_H * 2*pi*f_bw)"), ("ki", "V/(A*s)", "0 (SRM_R_OHM * 2*pi*f_bw)"),
                    ("f_bw", "Hz", "0 (pwm_hz / 20)"), *_SHARED_PARAMS],
    "tsf": [("theta_on", "electrical deg from unaligned", "15"), ("overlap", "electrical deg", "30"),
            ("kp", "V/A", "0 (SRM_L_MIN_H * 2*pi*f_bw)"), ("ki", "V/(A*s)", "0 (SRM_R_OHM * 2*pi*f_bw)"),
            ("f_bw", "Hz", "0 (pwm_hz / 20)"), *[p for p in _SHARED_PARAMS if p[0] not in ("theta_on", "theta_off")]],
}
