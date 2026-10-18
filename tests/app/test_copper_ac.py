import json

import numpy as np
import pytest
from conftest import make_8_6

from srmapp.copper import ac_copper_loss
from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.winding import wire_windings
from srmapp.wire import LitzWire, RoundWire, RectangularWire
from srmcore.materials.library import load_material

P = make_8_6()
ALPHA = load_material("copper").temperature_coefficient


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _setup(d=1.0e-3, **kw):
    wire = RoundWire(diameter=d, outer_diameter=d * 1.08)
    req = _req(wires=[wire], phase_current_a=50.0, **kw)
    return wire, wire_windings(P, req, 0, 40e6)[0]


def _loss(wire, w, f, b_amp, d_scale=1.0, temperature=120.0):
    n = 64
    t = np.arange(n) / n
    current = 30.0 * np.sin(2 * np.pi * t)
    b = np.zeros((n, 4, 2))
    b[:, :, 0] = b_amp * np.sin(2 * np.pi * t)[:, None]
    return ac_copper_loss(w, wire, current, 1 / f, b, np.array(["a", "a", "b", "b"]), np.ones(4) * 1e-5, P,
                          temperature)


def test_resistance_follows_temperature():
    _, w20 = _setup()
    r = lambda t: est.series_resistance(P, w20.turns, w20.copper_area, t)
    assert r(120.0) / r(20.0) == pytest.approx(1 + ALPHA * 100)
    assert w20.resistance == pytest.approx(r(120.0) / w20.paths**2)
    hot = wire_windings(P, _req(wires=[RoundWire(diameter=1e-3, outer_diameter=1.08e-3)], phase_current_a=50.0,
                                winding_temperature_c=20.0), 0, 40e6)[0]
    assert hot.resistance == pytest.approx(r(20.0) / hot.paths**2)


def test_ac_tends_to_zero_at_low_frequency():
    wire, w = _setup()
    dc = 0.5 * 30.0**2 * w.resistance * P.n_phases
    assert _loss(wire, w, 1.0, 1e-3) < 1e-6 * dc


def test_proximity_scales_d4_f2():
    w1, win = _setup(1.0e-4)
    w2 = RoundWire(diameter=2.0e-4, outer_diameter=2.16e-4)
    # tiny strands at low f: skin negligible, proximity dominates and follows d^4 f^2
    base = _loss(w1, win, 50.0, 0.5)
    assert _loss(w2, win, 50.0, 0.5) == pytest.approx(16 * base, rel=0.02)
    assert _loss(w1, win, 100.0, 0.5) == pytest.approx(4 * base, rel=0.02)


def test_density_mode_skips_ac():
    _, w = _setup()
    assert ac_copper_loss(w, None, np.ones(8), 0.01, np.zeros((8, 2, 2)), np.array(["a", "b"]), np.ones(2), P,
                          120.0) is None


def test_other_wires_use_equivalent_diameter():
    _, w = _setup()
    litz = LitzWire(strand_diameter=1e-4, strands=10, outer_diameter=1e-3)
    rect = RectangularWire(width=2e-3, height=1e-3, insulation=1e-4)
    assert _loss(litz, w, 400.0, 0.5) > 0 and _loss(rect, w, 400.0, 0.5) > _loss(litz, w, 400.0, 0.5)


def test_default_temperature_and_old_setup():
    assert _req().winding_temperature_c == 120.0
    data = json.loads(_req().model_dump_json())
    data.pop("winding_temperature_c")
    assert Requirements.model_validate(data).winding_temperature_c == 120.0
