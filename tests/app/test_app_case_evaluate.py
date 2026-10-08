from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.case import CaseInputs, FixedWinding, evaluate_design, map_cache_hit, map_request, validate_case
from srmapp.requirements import Requirements
from srmapp.sizing.generator import REFERENCE_TURNS
from srmcore.maps import build_map
from srmcore.model.design import Design, MeshSettings

THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _inputs(req=None, **kw):
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    return CaseInputs(requirements=req or _req(), design=design, **kw)


def _fake_map(design, i_max, **kw):
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, i_max, 9))


def _evaluate(inputs, **kw):
    with mock.patch("srmapp.evaluate.build_map", side_effect=_fake_map) as bm, \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        return evaluate_design(inputs, **kw), bm


def test_fixed_with_the_auto_winding_reproduces_auto():
    req = _req(wires=[THICK], phase_current_a=100.0)
    auto, _ = _evaluate(_inputs(req))
    w = auto.winding
    assert auto.status == "ok" and w is not None
    fixed, _ = _evaluate(_inputs(req, winding=FixedWinding(turns=w.turns, strands=w.strands, paths=w.paths,
                                                             wire=w.wire)))
    assert fixed.winding == auto.winding
    assert fixed.torque_ratio == pytest.approx(auto.torque_ratio)
    assert fixed.power_ratio == pytest.approx(auto.power_ratio)
    assert fixed.peak_power_w == pytest.approx(auto.peak_power_w)
    assert len(fixed.scan) == 1


def test_fixed_density_winding_is_evaluated_alone():
    inputs = _inputs(winding=FixedWinding(turns=10))
    e, bm = _evaluate(inputs)
    assert e.status == "ok" and (e.winding.turns, e.winding.paths, e.winding.wire) == (10, 1, None)
    assert len(e.scan) == 1
    _, i_map, stage = map_request(inputs)
    assert i_map == pytest.approx(stage.i_map)      # a density winding carries exactly the stage-1 ampere-turns


def test_fixed_beyond_the_search_range_extends_the_map():
    # a 1 A/mm2 peak cap limits the search to 150 A-turns; the user's 600 A-turns winding still gets its map
    req = _req(wires=[THICK], phase_current_a=100.0)
    inputs = _inputs(req, j_peak_max=1e6, winding=FixedWinding(turns=6, strands=1, paths=1, wire=0))
    _, i_map, stage = map_request(inputs)
    assert stage.mmf == pytest.approx(150.0)
    assert i_map == pytest.approx(6 * 100.0 / REFERENCE_TURNS)
    e, bm = _evaluate(inputs)
    assert bm.call_args.args[1] == pytest.approx(6 * 100.0 / REFERENCE_TURNS)
    assert e.status == "ok" and e.winding.turns == 6
    assert map_request(_inputs(req, j_peak_max=1e6))[1] == pytest.approx(stage.mmf / REFERENCE_TURNS)
    with pytest.raises(ValueError):
        map_request(_inputs(_req(wires=[THICK], phase_current_a=1e6)))     # no winding fits in Auto mode


def test_stage_one_rejection_is_a_note_not_a_stop():
    e, _ = _evaluate(_inputs(_req(peak_torque_nm=1e4, peak_power_w=3.14159e6), winding=FixedWinding(turns=10)))
    assert e.status == "ok" and e.error.startswith("stage 1: ") and not e.feasible


def test_map_cache_hit(tmp_path):
    inputs = _inputs()
    design, i_map, _ = map_request(inputs)
    assert not map_cache_hit(inputs, tmp_path, solver="skfem_reference")
    with mock.patch("srmcore.maps.api.run_map", side_effect=lambda *a, **kw: _fake_map(None, i_map)), \
            mock.patch("srmcore.maps.api.build_machine_mesh"):
        build_map(design, i_map, solver="skfem_reference", workers=1, cache_dir=tmp_path)
    assert map_cache_hit(inputs, tmp_path, solver="skfem_reference")
    # a map for another current range or grid is not a hit
    assert not map_cache_hit(_inputs(_req(wires=[THICK], phase_current_a=100.0)), tmp_path, solver="skfem_reference")
    with mock.patch("srmcore.maps.api.run_map", side_effect=lambda *a, **kw: _fake_map(None, i_map)), \
            mock.patch("srmcore.maps.api.build_machine_mesh"):
        build_map(design, i_map, solver="skfem_reference", workers=1, cache_dir=tmp_path / "other", n_angles=30)
    assert not map_cache_hit(inputs, tmp_path / "other", solver="skfem_reference")


@pytest.mark.slow
def test_validate_case_8_6_screening_label_none():
    pytest.importorskip("ngsolve")
    v = validate_case(_inputs())
    assert v.label is None
