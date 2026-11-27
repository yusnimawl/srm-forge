import numpy as np
import pytest

import kiyota_18_12 as k18
import kiyota_thermal as kt
from srmapp.sizing.estimates import series_resistance
from srmapp.thermal_network import _tri_area
from srmcore.materials.library import load_material
from srmcore.thermal.model import Temperatures

R_USED = k18.R_PHASE_20C
HOLD_A = 140.7
CU = load_material("copper")


@pytest.fixture(scope="module")
def case():
    return kt.build("screening")


def test_trace_integral():
    t = np.linspace(0.0, 20.0, 200001)
    assert np.trapezoid(kt.current(t) ** 2, t) == pytest.approx(11.12 * HOLD_A ** 2, rel=0.005)


def test_adiabatic_copper_heating(case):
    r = kt.rig(case, R_USED, iron_w=0.0, mech=None)
    res = kt.run(r, dt=0.05, t_end=2.0, current_fn=lambda t: HOLD_A)
    j = HOLD_A / kt.TURN_AREA
    r_model = series_resistance(case.machine, k18.TURNS_PER_POLE, kt.TURN_AREA, 20.0)
    c = CU.thermal.specific_heat
    mean_c = kt.START_C + res.end_peak_k / 2
    expect = j ** 2 * CU.resistivity_at(mean_c) / (CU.density * c) * 2.0 * R_USED / r_model
    assert res.end_peak_k == pytest.approx(expect, rel=0.02)


def test_load_balance(case):
    r = kt.rig(case, R_USED)
    d, net = case.domain, r.net
    t = Temperatures(np.full(len(d.nodes), kt.START_C), {e: kt.START_C for e in net.end_lumps.values()})
    load = r.load(HOLD_A)(t)
    total = float(np.sum(load.element_w_per_m3 * _tri_area(d.nodes, d.triangles) * case.machine.stack_length)) + sum(load.lump_w.values())
    copper = case.machine.n_phases * HOLD_A ** 2 * R_USED * CU.resistivity_at(kt.START_C) / CU.resistivity_at(kt.T_REF_C)
    assert total == pytest.approx(copper + kt.M_IRON_W / 3.2 + kt.MECH_W, rel=1e-9)
