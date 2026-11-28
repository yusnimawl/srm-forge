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


def test_raises_after_the_stroke_cap(monkeypatch):
    ctx, asked, _ = make(monkeypatch, iron_w=lambda n: 100.0 * n, torque_avg=lambda ask: 0.0)   # DRAG_MAX_STROKES strokes
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


def test_secant_converges_where_plain_steps_would_not(monkeypatch):
    k = 0.8      # need(a) = T f + k a: a plain step shrinks the error by 0.8 only
    f, ik = FACTOR, 1.0
    ctx, asked, _ = make(monkeypatch, iron_w=lambda n: 0.0)
    ctx.stroke = lambda rpm, a: (asked.append(a), (types.SimpleNamespace(torque_avg=a),
                                                    types.SimpleNamespace(iron_w=k * a * OMEGA / (f * ik))))[1]
    monkeypatch.setattr(th, "mechanical_loss", lambda *a, **kw: types.SimpleNamespace(total_w=0.0))
    ctx.load_at(RPM, frozenset())(2.0)
    assert len(asked) <= 4 and asked[-1] == pytest.approx(2.0 * f / (1 - k), rel=2e-3)
    plain = 2.0 * f
    for _ in range(th.DRAG_MAX_STROKES):
        plain = 2.0 * f + k * plain
    assert abs(plain - 2.0 * f / (1 - k)) > 2e-3 * 2.0 * f / (1 - k)      # six plain steps would still miss


def test_none_at_a_later_attempt_returns_none(monkeypatch):
    ctx, asked, _ = make(monkeypatch, torque_avg=lambda ask: 0.0)
    real = ctx.stroke
    ctx.stroke = lambda rpm, t: real(rpm, t) if not asked else None
    assert ctx.load_at(RPM, frozenset())(2.0) is None


def test_shaft_top_is_reached_and_stays_within_the_em_top(monkeypatch):
    ctx, asked, _ = make(monkeypatch, iron_w=lambda n: IRON_W)
    em_top = 5.0
    top, fell = ctx.shaft_top(RPM, frozenset(ROWS), em_top)
    assert not fell
    loss = (IRON_W * IRON_FACTOR + MECH[True]) / OMEGA
    assert top == pytest.approx((em_top / FACTOR - loss) * (1 - th.DRAG_TOL))
    asked.clear()
    assert ctx.load_at(RPM, frozenset(ROWS))(top) is not None
    assert max(asked) <= em_top


def test_rate_context_passes_the_shaft_top(monkeypatch):
    ctx, asked, _ = make(monkeypatch)
    em_top = 5.0
    ctx.setup = types.SimpleNamespace(placeholder=False)
    ctx.machine = ctx.limit = None
    ctx.envelope_at = lambda speeds: {rpm: em_top for rpm in speeds}
    ctx.strokes, ctx.check, ctx.solver_for = {}, lambda: None, lambda rpm, rows: None
    monkeypatch.setattr(th, "mechanical_loss", lambda *a, **kw: types.SimpleNamespace(
        total_w=MECH[kw.get("unfavourable", False)], notes=[]))
    ctx.limit = 120.0
    seen = []

    def stop(rpm, envelope, *a, **kw):
        seen.append(envelope)
        raise KeyboardInterrupt

    monkeypatch.setattr(th, "rate_speed", stop)
    with pytest.raises(KeyboardInterrupt):
        th.rate_context(ctx)
    expected, _ = ctx.shaft_top(th.rating_speeds(ctx.req, 6)[0], frozenset(), em_top)
    assert seen[0] == pytest.approx(expected) and seen[0] < em_top / FACTOR - 1e-6


def test_secant_ask_above_the_em_top_falls_back_to_the_plain_step(monkeypatch):
    em_top, share, jump_at = 5.0, 0.1, 0.95 * 5.0
    ctx, asked, _ = make(monkeypatch)
    solved = []

    def stroke(rpm, a):
        if a > em_top:
            return None
        solved.append(a)
        jump = 1.1 if a > jump_at else 1.0     # single pulse to continuous conduction
        return (types.SimpleNamespace(torque_avg=a),
                types.SimpleNamespace(iron_w=share * a * jump * OMEGA / FACTOR))

    ctx.stroke = stroke
    monkeypatch.setattr(th, "mechanical_loss", lambda *a, **kw: types.SimpleNamespace(total_w=0.0))
    top, fell = ctx.shaft_top(RPM, frozenset(), em_top)
    solved.clear()
    assert not fell and ctx.load_at(RPM, frozenset())(top) is not None
    assert max(solved) <= em_top and len(solved) >= 3
