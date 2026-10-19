"""Running a compiled controller against the simulator core."""

from __future__ import annotations

import ctypes as C
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from srmsil import _abi
from srmsil.build import compile_host, controller_sources
from srmsil.scenario import Scenario
from srmsil.tables import MotorData, sim_tables

TRACE_CAP = 2_000_000
ADC_BITS = 16
ADC_AMPS_PER_COUNT = 0.005

_C_DIR = Path(__file__).parent / "c"
_SIM_DIR = _C_DIR / "sim"


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


def sim_library(controller_dir: Path, header_dir: Path, cache_dir: Path) -> Path:
    sources = [*sorted(_SIM_DIR.glob("*.c")), *controller_sources(Path(controller_dir))]
    return compile_host(sources, [_C_DIR, _SIM_DIR, Path(header_dir), Path(controller_dir)],
                        Path(cache_dir) / "sil" / "build")


def _ptr(a: np.ndarray, ctype):
    return a.ctypes.data_as(C.POINTER(ctype))


def _run_loaded(lib_path: Path, m: MotorData, scenario: Scenario) -> SimResult:
    """Load the library and run it. Call only in a child process: the library holds controller code and C state."""
    lib = C.CDLL(str(Path(lib_path).resolve()))
    _abi.bind(lib)
    for name, value in scenario.params.items():
        if lib.srm_sim_param(name.encode(), value) != 0:
            raise ValueError(f"controller rejected parameter {name!r}")
    tab = sim_tables(m)
    q = m.n_phases
    n_steps = scenario.n_steps
    stride = math.ceil(n_steps / TRACE_CAP)
    n = math.ceil(n_steps / stride)
    rpm = 2 * math.pi / 60
    cv = scenario.command_value * (rpm if scenario.command_mode == "speed" else 1.0)
    sc = scenario.converter
    cfg = _abi.Config(
        resistance=m.resistance, bus_voltage=scenario.bus_voltage or m.bus_voltage, dt=scenario.dt,
        speed=scenario.speed_rpm * rpm, theta0=scenario.theta0, inertia=scenario.inertia,
        friction=scenario.friction, load=scenario.load, load_step=scenario.load_step,
        load_step_time=scenario.load_step_time, pwm_hz=scenario.pwm_hz, isr_hz=scenario.resolved_isr_hz,
        compute_delay=scenario.resolved_compute_delay, command_value=cv, v_switch=sc.v_switch, v_diode=sc.v_diode,
        dead_time=sc.dead_time, turn_on_delay=sc.turn_on_delay, turn_off_delay=sc.turn_off_delay,
        adc_amps_per_count=ADC_AMPS_PER_COUNT, n_steps=n_steps, trace_stride=stride, n_phases=q,
        n_rotor_poles=m.n_rotor_poles, mode=int(scenario.mode == "dynamic"), command_mode=int(scenario.command_mode == "speed"),
        encoder_cpr=scenario.sensors.encoder_cpr, adc_bits=ADC_BITS, adc_offset_counts=0, seed=scenario.seed)
    cur, trq, wf = (np.ascontiguousarray(a, dtype=np.float64) for a in (tab.current, tab.torque, tab.w_field))
    ctab = _abi.Tables(theta_step=tab.theta_step, psi_step=tab.psi_step, psi_max=tab.psi_max, i_max=tab.i_max,
                       n_theta=cur.shape[0], n_psi=cur.shape[1], current=_ptr(cur, C.c_double),
                       torque=_ptr(trq, C.c_double), w_field=_ptr(wf, C.c_double))
    scalars = {k: np.zeros(n) for k in ("t", "theta", "omega", "torque", "encoder")}
    phased = {k: np.zeros((q, n), np.float32) for k in ("i", "psi", "v", "adc_i")}
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
    if rc == -2:
        raise RuntimeError("the controller queued more gate commands than the simulator can delay; "
                           "shorten compute_delay or issue fewer commands")
    if rc != 0:
        raise RuntimeError(f"simulator rejected the configuration (code {rc})")
    got = ctrace.n_samples
    traces = {k: a[:got] for k, a in scalars.items()}
    traces.update({k: a[:, :got] for k, a in {**phased, **gates}.items()})
    ws = max(csum.window_steps, 1)
    mean_t = csum.torque_sum / ws
    ripple = 100 * (csum.torque_max - csum.torque_min) / abs(mean_t) if abs(mean_t) > 1e-12 else math.nan
    e_in = csum.energy_in
    err = abs(e_in - csum.energy_mech - csum.energy_copper - (csum.w_field_end - csum.w_field_start)) / max(abs(e_in), 1e-12)
    summary = SimSummary(
        mean_torque=mean_t, ripple_pct=ripple, i_rms=np.sqrt(np.array(csum.i2_sum[:q]) / ws),
        copper_loss=csum.copper_sum / ws, power_in=csum.power_in_sum / ws, power_mech=csum.power_mech_sum / ws,
        beyond_map_fraction=csum.beyond_map_steps / n_steps, energy_error=err, roundtrip_error=tab.roundtrip_error)
    return SimResult(traces, summary, scenario, "", "", "")
