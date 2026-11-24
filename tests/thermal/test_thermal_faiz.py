"""Faiz 8/6 stator case (R5 gate V2): geometry against Table I, the loads, the heat balance and the frame models."""
import numpy as np
import pytest
from dataclasses import replace

import faiz_8_6 as F
from srmcore.thermal.model import LumpLink, Temperatures
from srmcore.thermal.solve import ThermalSolver


@pytest.fixture(scope="module")
def case():
    return F.build("screening")


def test_every_element_has_a_part(case):
    assert set(case.part) == {"pole", "yoke", "winding", "liner", "wedge"}


def test_areas_against_table_i(case):
    # Table I, p. 2928: yoke 4418 mm2, slot 2980 mm2 (winding + liner + wedge)
    assert case.part_area("yoke") * 1e6 == pytest.approx(4418, rel=0.005)
    slot = sum(case.part_area(n) for n in ("winding", "liner", "wedge")) * 1e6
    assert slot == pytest.approx(2980, rel=0.005)


def test_load_is_table_iv(case):
    q = F.load(case).element_w_per_m3
    assert (q * case.area).sum() * F.STACK == pytest.approx(40.9, rel=1e-9)


@pytest.mark.parametrize("frame", F.FRAMES)
def test_steady_heat_balance(case, frame):
    p = F.problem(case, 20.0, frame=frame)
    s = ThermalSolver(p)
    t = s.steady(lambda _: F.load(case), tol_k=1e-9)
    out = sum(s.heat_to_fixed(t).values())
    assert out == pytest.approx(40.9, rel=1e-6)


def test_frame_models_differ_and_table_v_values(case):
    pp, pv = F.problem(case, 20.0, frame="printed"), F.problem(case, 20.0, frame="table_v")
    cap = {l.name: l.capacity for l in pv.lumps}["frame"]
    g = [l.conductance for l in pv.links if isinstance(l, LumpLink)][0]
    assert cap == F.TABLE_V_C1 and g == pytest.approx(1 / F.TABLE_V_R1)
    assert {l.name: l.capacity for l in pp.lumps}["frame"] != cap
    with pytest.raises(ValueError):
        F.problem(case, 20.0, frame="x")


def test_with_air_changes_only_inside_air(case):
    p = F.problem(case, 20.0)
    q = F.with_air(p, 45.0)
    for a, b in zip(p.lumps, q.lumps):
        assert (a == b) == (a.name != "inside_air")
        if a.name == "inside_air":
            assert b.fixed_c == 45.0
    assert q.links == p.links
