import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from sil_fixtures import analytic_motor, run_in_child

from srmapp.drive.envelope import _simulate, _tables
from srmsil.run import _run_loaded, sim_library
from srmsil.scenario import ConverterSettings, Scenario
from srmsil.tables import ctrl_tables, write_header

CTRL = Path(__file__).parent / "controllers"
IDEAL = ConverterSettings(v_switch=0, v_diode=0, dead_time=0, turn_on_delay=0, turn_off_delay=0)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("sil_core")


def run(cache, controller, m, tag, **scn):
    hdr = cache / f"hdr_{tag}"
    hdr.mkdir(exist_ok=True)
    write_header(m, ctrl_tables(m), hdr / "srm_motor_tables.h")
    lib = sim_library(CTRL / controller, hdr, cache)
    return run_in_child(_run_loaded, lib, m, Scenario(**scn))


def phase_angle(res, k, m):
    return np.mod(res.traces["theta"] - k * m.stroke, m.pole_pitch)


def test_single_pulse_matches_envelope(cache):
    m = analytic_motor(bus_voltage=24.0)
    tau = m.pole_pitch
    rpm, dt = 1000.0, 0.25e-6
    period = tau / (rpm * 2 * math.pi / 60)
    res = run(cache, "open_loop", m, "sat", speed_rpm=rpm, duration=3 * period, dt=dt, isr_hz=1e6, compute_delay=dt,
              sensors={"encoder_cpr": 2**20}, converter=IDEAL, params={"theta_on": 0.5 * tau, "theta_off": 0.65 * tau})
    psi, t = res.traces["psi"], res.traces["t"]
    for k in range(m.n_phases):
        peak = psi[k].max()
        assert peak > 0.01
        late = phase_angle(res, k, m) > 0.97 * tau
        assert psi[k][late].max() < 0.01 * peak
    last2 = t >= period - 1e-12
    mean_sim = res.traces["torque"][last2].mean()

    ns = SimpleNamespace(circuits=["A"], excited="A", currents=m.currents, psi=m.psi[..., None],
                         torque_arkkio=m.torque, angles=m.angles)
    # The envelope's explicit angle stepping is first order: at its default 181 points it is 1.2 % above its own
    # converged value, so the comparison uses a grid fine enough for the discretisation to drop below 0.2 %.
    n_theta = 2881
    tab = _tables(ns, tau, float(m.currents[-1]), n_theta)
    omega = rpm * 2 * math.pi / 60
    on, off = np.array([round(0.5 * (n_theta - 1))]), np.array([round(0.65 * (n_theta - 1))])
    w_t, _, _, valid, psi_e, _ = _simulate(tab, omega, 24.0, m.resistance, on, off, trace=True)
    assert valid[0]
    assert (psi_e[1:, 0] < 0.98 * tab.psi[1:, -1]).all()      # the envelope's current limit never acts
    mean_env = m.n_phases * w_t[0] / tau
    assert mean_sim == pytest.approx(mean_env, rel=0.01)


def test_dt_convergence(cache):
    m = analytic_motor(bus_voltage=24.0)
    tau = m.pole_pitch
    out = []
    for dt in (1e-6, 0.5e-6):
        res = run(cache, "open_loop", m, "sat", speed_rpm=1000.0, duration=2 * tau / (1000 * 2 * math.pi / 60), dt=dt,
                  isr_hz=1e5, compute_delay=10e-6, sensors={"encoder_cpr": 2**20}, converter=IDEAL,
                  params={"theta_on": 0.5 * tau, "theta_off": 0.65 * tau})
        out.append(res.summary)
    assert out[0].mean_torque == pytest.approx(out[1].mean_torque, rel=0.002)
    assert out[0].i_rms == pytest.approx(out[1].i_rms, rel=0.002)


def test_energy_balance(cache):
    m = analytic_motor(bus_voltage=24.0, saturating=False)
    tau = m.pole_pitch
    res = run(cache, "open_loop", m, "lin", speed_rpm=1000.0, duration=0.03, isr_hz=1e5, compute_delay=10e-6,
              sensors={"encoder_cpr": 2**20}, params={"theta_on": 0.5 * tau, "theta_off": 0.65 * tau})
    assert res.summary.power_in > 1.0
    assert res.summary.energy_error < 0.005


def test_small_signal_l_inc(cache):
    m = analytic_motor(saturating=False)
    theta0 = 0.3 * m.pole_pitch
    res = run(cache, "volt_step", m, "lin", mode="fixed", speed_rpm=0.0, duration=50e-6, bus_voltage=1.0,
              theta0=theta0, converter=IDEAL)
    n20 = int(round(20e-6 / 0.5e-6))
    slope = res.traces["i"][0][n20] / res.traces["t"][n20]
    l_inc = 1e-3 + 7e-3 * (1 + math.cos(m.n_rotor_poles * theta0)) / 2
    assert slope == pytest.approx(1.0 / l_inc, rel=0.02)


def test_diode_clamp_and_voltages(cache):
    m = analytic_motor(bus_voltage=24.0)
    tau = m.pole_pitch
    res = run(cache, "open_loop", m, "sat", speed_rpm=1000.0, duration=0.01, isr_hz=1e5, compute_delay=10e-6,
              sensors={"encoder_cpr": 2**20}, params={"theta_on": 0.5 * tau, "theta_off": 0.65 * tau})
    tr = res.traces
    assert (tr["i"] >= 0).all() and (tr["psi"] >= 0).all()
    i, v, u, l = tr["i"][0], tr["v"][0], tr["gate_u"][0], tr["gate_l"][0]
    on = (u == 1) & (l == 1)
    assert on.any() and (v[on] == 22.0).all()
    off = (u == 0) & (l == 0)
    assert (v[off & (i > 1e-6)] == -26.0).all()
    assert (i[off & (v == 0)] < 1e-6).all()
    assert ((v == 0) & off & (i == 0)).any()
    assert i[-1] == 0 and tr["psi"][0][-1] == 0


def test_switch_delays(cache):
    m = analytic_motor(bus_voltage=24.0)
    tau = m.pole_pitch
    cv = ConverterSettings(v_switch=0, v_diode=0, dead_time=1e-6, turn_on_delay=1e-6, turn_off_delay=0)
    res = run(cache, "open_loop", m, "sat", speed_rpm=0.0, theta0=0.5 * tau, duration=500e-6, isr_hz=1e4,
              sensors={"encoder_cpr": 2**20}, converter=cv, params={"theta_on": 0.4 * tau, "theta_off": 0.6 * tau})
    v, t = res.traces["v"][0], res.traces["t"]
    first = t[np.argmax(v > 0)]
    isr_time, compute_delay = 0.5 / 1e4, 1 / 1e4
    assert first == pytest.approx(isr_time + compute_delay + 2e-6, abs=0.5e-6)
    assert (res.traces["v"][1:] == 0).all()


def test_beyond_map_flagged(cache):
    m = analytic_motor()
    res = run(cache, "volt_step", m, "sat", speed_rpm=0.0, duration=0.02, dt=1e-6, bus_voltage=400.0)
    assert res.summary.beyond_map_fraction > 0
    for a in res.traces.values():
        assert np.isfinite(a).all()


def test_standstill_fixed(cache):
    m = analytic_motor()
    tau = m.pole_pitch
    res = run(cache, "open_loop", m, "sat", speed_rpm=0.0, theta0=0.55 * tau, duration=0.002, dt=1e-6,
              sensors={"encoder_cpr": 4096}, params={"theta_on": 0.4 * tau, "theta_off": 0.7 * tau})
    for a in res.traces.values():
        assert np.isfinite(a).all()
    assert res.traces["torque"].max() > 0


def test_standstill_dynamic_accelerates(cache):
    m = analytic_motor()
    tau = m.pole_pitch
    res = run(cache, "open_loop", m, "sat", mode="dynamic", speed_rpm=0.0, theta0=0.55 * tau, duration=0.002,
              dt=1e-6, params={"theta_on": 0.4 * tau, "theta_off": 0.7 * tau})
    assert res.traces["omega"][-1] > 0
    assert np.isfinite(res.traces["omega"]).all()


def test_max_steps_rejected():
    with pytest.raises(ValueError):
        Scenario(duration=100.0, dt=1e-6)


def test_unknown_param_rejected(cache):
    with pytest.raises(ValueError, match="nope"):
        run(cache, "open_loop", analytic_motor(), "sat", params={"nope": 1.0})
