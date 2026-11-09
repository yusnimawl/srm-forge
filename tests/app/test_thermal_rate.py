import time
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.case import CaseInputs, FixedWinding, evaluate_design
from srmapp.cooling import ROWS, CoolingSetup
from srmapp.requirements import Requirements
from srmapp.thermal import rate
from srmcore.model.design import Design, MeshSettings, RegionMaterials

WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)
IRON = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
DESIGN = Design(machine=make_8_6(materials=IRON, lamination_thickness=1.0e-4), mesh=MeshSettings(preset="screening"))


def _fake_map(design, i_max, **kw):
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, i_max, 9))


@pytest.fixture(scope="module")
def case():
    req = Requirements(peak_power_w=670.0, peak_torque_nm=3.2, base_speed_rpm=2000.0, max_speed_rpm=6000.0,
                       wires=[WIRE], phase_current_a=15.0, continuous_power_w=300.0)
    inputs = CaseInputs(requirements=req, design=DESIGN, winding=FixedWinding(turns=8, strands=1, paths=1, wire=0))
    with mock.patch("srmapp.evaluate.build_map", side_effect=_fake_map):
        evaluation = evaluate_design(inputs)
    assert evaluation.status == "ok"
    return inputs, evaluation


def _rate(case, cache_dir, **kw):
    t = time.time()
    with mock.patch("srmapp.thermal.build_map", side_effect=_fake_map):
        out = rate(*case, n_angles=12, n_speeds=1, cache_dir=cache_dir, **kw)
    print(f"rate wall {time.time() - t:.0f} s")
    return out


@pytest.mark.slow
def test_rate_8_6(case, tmp_path):
    r = _rate(case, tmp_path)
    print(r)
    assert len(r.nominal) == 2
    for nom, rated in zip(r.nominal, r.rated):
        assert 0 <= rated.continuous_nm <= nom.continuous_nm <= nom.envelope_nm
        assert rated.peak_nm <= nom.peak_nm
        assert nom.continuous_hot_spot.temperature_c <= r.limit_c + 0.5
    assert {s.row for s in r.shares} == set(ROWS)
    assert all(s.hot_spot_rise_k >= 0 for s in r.shares)
    assert any("placeholder" in n for n in r.notes)
    assert r.stress.status in ("ok", "no_fillet")
    assert r.n_strokes > 0


@pytest.mark.slow
def test_rerate_reuses_strokes(case, tmp_path):
    first = _rate(case, tmp_path)
    n = len(list((tmp_path / "strokes").glob("*.npz")))
    second = _rate(case, tmp_path, em_budget=None)
    assert len(list((tmp_path / "strokes").glob("*.npz"))) == n
    assert second.rated[0].continuous_nm == first.rated[0].continuous_nm
