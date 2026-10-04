"""Fast checks of the M5c FEMM comparison definitions (no meshing, no solving)."""
import math

import numpy as np
import pytest

import femm_machines as fm
from srmcore.model.validator import require_valid


@pytest.mark.parametrize("name", list(fm.MACHINES))
def test_designs_pass_validator(name):
    with fm.waivers(name):
        require_valid(fm.design(name))


def test_jiang_needs_the_waiver():
    from srmcore.model.errors import InputError
    with pytest.raises(InputError):
        require_valid(fm.design("jiang_24_16"))


def test_krishnan_points_match_the_spike():
    d = fm.design("krishnan_8_6")
    assert fm.knee_current(d.machine) == pytest.approx(7.75, rel=1e-3)
    assert fm.currents(d.machine) == (3.1, 13.0, 30.0)
    pts = fm.points(d)
    assert len(pts) == 21
    angles = sorted({a for a, _ in pts})
    assert angles[0] == 0.0
    assert angles[-1] == pytest.approx(math.pi / 6, abs=math.radians(0.5))
    assert angles[1] == pytest.approx(math.radians(4.0), abs=math.radians(0.5))


def test_tolerance_rule():
    d = fm.design("krishnan_8_6")
    assert fm.tolerance(d, math.radians(15), 13.0) == 0.03
    assert fm.tolerance(d, math.radians(4), 13.0) == 0.05
    assert fm.tolerance(d, math.radians(28), 3.1) == 0.05
    assert fm.tolerance(d, math.radians(15), 30.0) == 0.05


def test_rated_current_is_mid_range_for_every_machine():
    for name in fm.MACHINES:
        d = fm.design(name)
        i_rated = fm.currents(d.machine)[1]
        u = math.pi / d.machine.n_rotor_poles
        assert fm.tolerance(d, u / 2, i_rated) == 0.03


def test_bh_table_dense_monotone_to_4_tesla():
    b, h = fm.bh_table("M19")
    assert len(b) >= 300
    assert b[0] == 0.0 and h[0] == 0.0 and b[-1] == pytest.approx(4.0)
    assert np.all(np.diff(b) > 0) and np.all(np.diff(h) > 0)


def test_hashes_are_stable_and_sensitive():
    d = fm.design("krishnan_8_6")
    assert fm.design_sha256(d) == fm.design_sha256(fm.design("krishnan_8_6"))
    assert fm.bh_sha256(d) == fm.bh_sha256(fm.design("krishnan_8_6"))
    other = d.model_copy(update={"machine": d.machine.model_copy(update={"air_gap": 0.00051})})
    assert fm.design_sha256(other) != fm.design_sha256(d)
