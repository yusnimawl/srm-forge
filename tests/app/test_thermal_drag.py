import math
import types

import numpy as np
import pytest

from srmapp import thermal as th
from srmapp.cooling import ROWS
from srmapp.requirements import Requirements

RPM = 3000.0
OMEGA = RPM * 2 * math.pi / 60
FACTOR = 1.1
IRON_FACTOR = 2.0
IRON_W = 100.0
MECH = {False: 10.0, True: 30.0}     # nominal, unfavourable mechanical loss in W


def make(monkeypatch, iron_w=IRON_W, torque_avg=lambda ask: ask):
    ctx = th.ThermalContext.__new__(th.ThermalContext)
    ctx.req = Requirements(peak_power_w=1000.0, peak_torque_nm=3.0, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    ctx.domain = types.SimpleNamespace(triangles=np.zeros((3, 3)))
    ctx.static = ctx.hot = ctx.wire = ctx.machine = None
    ctx.limit = 120.0
    asked = []

    def stroke(rpm, torque):
        asked.append(torque)
        trace = types.SimpleNamespace(torque_avg=torque_avg(torque))
        return trace, types.SimpleNamespace(iron_w=iron_w(len(asked)) if callable(iron_w) else iron_w)

    ctx.stroke = stroke
    ctx.at = lambda rpm, rows: (types.SimpleNamespace(torque_factor=FACTOR, iron_factor=IRON_FACTOR if "iron" in rows else 1.0),
                                types.SimpleNamespace())
    monkeypatch.setattr(th, "mechanical_loss",
                        lambda machine, bearing, rpm, unfavourable: types.SimpleNamespace(total_w=MECH[unfavourable]))
    heats = []
    monkeypatch.setattr(th, "point_heat", lambda *a: heats.append(a) or a)
    monkeypatch.setattr(th, "load_fn", lambda *a: a)
    return ctx, asked, heats


def test_stroke_covers_torque_plus_loss_torque(monkeypatch):
    ctx, asked, heats = make(monkeypatch)
    ctx.load_at(RPM, frozenset())(2.0)
    need = (2.0 + (IRON_W * 1.0 + MECH[False]) / OMEGA) * FACTOR
    assert asked == pytest.approx([2.0 * FACTOR, need])      # a constant loss ends after two strokes
    assert heats[0][8] == 1.0 and heats[0][-1].total_w == MECH[False]      # nominal: iron factor 1, nominal mechanical loss


def test_rated_set_takes_iron_factor_and_high_mechanical_band(monkeypatch):
    ctx, asked, heats = make(monkeypatch)
    ctx.load_at(RPM, frozenset(ROWS))(2.0)
    need = (2.0 + (IRON_W * IRON_FACTOR + MECH[True]) / OMEGA) * FACTOR
    assert asked == pytest.approx([2.0 * FACTOR, need])
    assert heats[0][8] == IRON_FACTOR and heats[0][-1].total_w == MECH[True]


def test_raises_after_four_strokes(monkeypatch):
    ctx, asked, _ = make(monkeypatch, iron_w=lambda n: 100.0 * n, torque_avg=lambda ask: 0.0)
    with pytest.raises(RuntimeError):
        ctx.load_at(RPM, frozenset())(2.0)
    assert len(asked) == th.DRAG_MAX_STROKES


def test_no_stroke_gives_none(monkeypatch):
    ctx, _, _ = make(monkeypatch)
    ctx.stroke = lambda rpm, torque: None
    assert ctx.load_at(RPM, frozenset())(2.0) is None


def test_zero_torque_solves_no_stroke(monkeypatch):
    ctx, asked, _ = make(monkeypatch)
    ctx.load_at(RPM, frozenset())(0.0)
    assert asked == []
