import math

import numpy as np
import pytest
from sil_fixtures import L_A, L_U, PSI_S, analytic_motor, call_in_child

from srmsil import build, tables


def _lookup(st, theta, psi):
    """Bilinear lookup of the current table (periodic in θ, linear extrapolation in ψ is in the table)."""
    n_theta, n_psi = st.current.shape
    x = (theta / st.theta_step) % n_theta
    j = int(x)
    fj = x - j
    y = psi / st.psi_step
    k = min(int(y), n_psi - 2)
    fk = y - k
    row = lambda r: st.current[r][k] * (1 - fk) + st.current[r][k + 1] * fk
    return row(j) * (1 - fj) + row((j + 1) % n_theta) * fj


def _L(theta, nr=6):
    return L_U + (L_A - L_U) * (1 + math.cos(nr * theta)) / 2


def test_roundtrip_error_small():
    assert tables.sim_tables(analytic_motor()).roundtrip_error < 1e-4


def test_current_matches_analytic():
    m = analytic_motor()
    st = tables.sim_tables(m)
    rng = np.random.default_rng(1)
    for _ in range(10):
        th = rng.uniform(0, m.pole_pitch)
        i = rng.uniform(1.0, 20.0)
        psi = PSI_S * math.tanh(_L(th) * i / PSI_S)
        assert _lookup(st, th, psi) == pytest.approx(i, rel=2e-3)


def test_extrapolates_beyond_map():
    st = tables.sim_tables(analytic_motor())
    for th in (0.0, 0.3):
        got = _lookup(st, th, 1.1 * st.psi_max)
        assert math.isfinite(got)
    # the table itself reaches psi_max; extrapolation continues the last slope
    row = st.current[0]
    slope = (row[-1] - row[-2]) / st.psi_step
    assert row[-1] + slope * 0.1 * st.psi_max > row[-1]


def test_w_field_linear():
    m = analytic_motor(saturating=False)
    st = tables.sim_tables(m)
    for j in (0, 100, 250, 400):
        th = j * st.theta_step
        for k in (100, 300, 511):
            psi = k * st.psi_step
            assert st.w_field[j, k] == pytest.approx(psi**2 / (2 * _L(th)), rel=1e-3)


def test_i_of_t_rules():
    m = analytic_motor()
    ct = tables.ctrl_tables(m)
    n = ct.i_of_t.shape[0]
    pp = m.pole_pitch
    falling = int(n * 0.25)       # sin(N_r θ) = 1: L falling, T < 0
    rising = int(n * 0.75)        # sin(N_r θ) = -1: L rising, T > 0
    assert np.all(ct.i_of_t[falling] == 0)
    row = ct.i_of_t[rising]
    assert np.all(np.diff(row) >= 0)
    th = rising * pp / n
    L = _L(th)
    dL = -(L_A - L_U) / 2 * 6 * math.sin(6 * th)
    n_t = row.size
    for j in range(1, n_t):
        i = float(row[j])
        x = L * i / PSI_S
        t = (-PSI_S**2 / L**2 * math.log(math.cosh(x)) + PSI_S / L * math.tanh(x) * i) * dL
        tj = j * ct.t_max / (n_t - 1)
        if tj <= t * 1.0001 or i < ct.i_max - 1e-3:
            assert t == pytest.approx(tj, rel=0.01)


def test_motor_data_from_json():
    m = analytic_motor()
    ev = {
        "map": {"angles": m.angles.tolist(), "currents": m.currents.tolist(),
                "psi": m.psi.tolist(), "torque": m.torque.tolist()},
        "winding": {"resistance": 0.7},
        "design": {"machine": {"n_phases": 4, "n_rotor_poles": 6}},
    }
    d = tables.motor_data_from_json(ev, 48.0)
    assert d.resistance == 0.7 and d.n_phases == 4 and d.n_rotor_poles == 6 and d.bus_voltage == 48.0
    assert d.psi.shape == (48, 21)
    assert d.stroke == pytest.approx(2 * math.pi / 6 / 4)
    for key in ("winding", "map"):
        bad = {k: v for k, v in ev.items() if k != key}
        with pytest.raises(ValueError):
            tables.motor_data_from_json(bad, 48.0)
        bad = {**ev, key: None}
        with pytest.raises(ValueError):
            tables.motor_data_from_json(bad, 48.0)


def test_header_compiles_and_matches(tmp_path):
    m = analytic_motor()
    ct = tables.ctrl_tables(m)
    inc = tmp_path / "inc"
    inc.mkdir()
    tables.write_header(m, ct, inc / "srm_motor_tables.h")
    pts = [(0.0, 0.0), (0.123, 1.3), (0.5, 0.4 * ct.t_max), (-0.2, 0.9 * ct.t_max), (1.0, 2 * ct.t_max)]
    calls = "".join(f"  if (k == {n}) return srm_i_of_t((float){a!r}, (float){b!r});\n" for n, (a, b) in enumerate(pts))
    src = tmp_path / "t.c"
    src.write_text(
        '#include "srm_motor_tables.h"\n#ifdef _WIN32\n__declspec(dllexport)\n#endif\n'
        f"double probe(double k) {{\n{calls}  return -1.0;\n}}\n")
    lib = build.compile_host([src], [inc], tmp_path / "out")
    tab = ct.i_of_t.astype(np.float64)
    n_th, n_t = tab.shape
    for n, (th, t) in enumerate(pts):
        u = (th / m.pole_pitch) % 1.0 * n_th
        j = int(u)
        fj = u - j
        t = min(max(t, 0.0), ct.t_max)
        y = t / ct.t_max * (n_t - 1)
        k = min(int(y), n_t - 2)
        fk = y - k
        r = lambda q: tab[q, k] * (1 - fk) + tab[q, k + 1] * fk
        want = r(j % n_th) * (1 - fj) + r((j + 1) % n_th) * fj
        assert call_in_child(lib, "probe", float(n)) == pytest.approx(want, rel=1e-5, abs=1e-6)
