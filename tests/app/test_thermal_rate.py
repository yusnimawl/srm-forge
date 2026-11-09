import time

import pytest
from conftest import make_8_6

from srmapp.case import CaseInputs, FixedWinding, evaluate_design
from srmapp.cooling import ROWS
from srmapp.requirements import Requirements
from srmapp.thermal import rate
from srmcore.model.design import Design, MeshSettings, RegionMaterials

WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)
IRON = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
DESIGN = Design(machine=make_8_6(materials=IRON, lamination_thickness=1.0e-4), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("rate")


@pytest.fixture(scope="module")
def case(cache_dir):
    # 24 turns at 20 A put the envelope near 3.4 Nm, where the default cooling binds at the hot-spot limit.
    req = Requirements(peak_power_w=628.0, peak_torque_nm=3.0, base_speed_rpm=2000.0, max_speed_rpm=6000.0,
                       wires=[WIRE], phase_current_a=20.0, continuous_power_w=100.0)
    inputs = CaseInputs(requirements=req, design=DESIGN, winding=FixedWinding(turns=24, strands=1, paths=1, wire=0))
    evaluation = evaluate_design(inputs, cache_dir=cache_dir)
    assert evaluation.status == "ok"
    return inputs, evaluation


def _rate(case, cache_dir):
    t = time.time()
    out = rate(*case, n_angles=12, n_speeds=1, cache_dir=cache_dir)
    print(f"rate wall {time.time() - t:.0f} s")
    return out


@pytest.fixture(scope="module")
def rating(case, cache_dir):
    return _rate(case, cache_dir)


@pytest.mark.slow
def test_rate_8_6(rating):
    r = rating
    print(r)
    assert len(r.nominal) == 2
    for nom, rated in zip(r.nominal, r.rated):
        assert 0 <= rated.continuous_nm <= nom.continuous_nm <= nom.envelope_nm
        assert rated.peak_nm <= nom.peak_nm
        assert nom.continuous_hot_spot.temperature_c <= r.limit_c + 0.5
    # the bisection stops at a bracket of 1 % of the envelope, about 1.2 K here, so "at the limit" means within 1.5 K
    assert any(n.continuous_nm < n.envelope_nm and n.continuous_hot_spot.temperature_c >= r.limit_c - 1.5
               for n in r.nominal), "the limit must bind at some speed"
    assert any(x.start_nm < x.continuous_nm and x.peak_nm > x.continuous_nm for x in r.rated)
    assert {s.row for s in r.shares} == set(ROWS)
    assert all(s.hot_spot_rise_k >= 0 for s in r.shares)
    assert any("placeholder" in n for n in r.notes)
    assert r.stress.status in ("ok", "no_fillet")
    assert r.n_strokes > 0


@pytest.mark.slow
def test_rerate_reuses_strokes(case, cache_dir, rating):
    n = len(list((cache_dir / "strokes").glob("*.npz")))
    assert n > 0
    second = _rate(case, cache_dir)
    assert len(list((cache_dir / "strokes").glob("*.npz"))) == n
    assert second.rated[0].continuous_nm == rating.rated[0].continuous_nm
