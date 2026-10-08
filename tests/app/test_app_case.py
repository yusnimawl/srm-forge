import pytest
from pydantic import ValidationError

from conftest import make_8_6, make_12_8, make_24_16
from srmapp.case import CaseInputs, FixedWinding, reference_design
from srmapp.pipeline import SearchSettings
from srmapp.references import REFERENCES
from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.generator import REFERENCE_TURNS
from srmapp.sizing.winding import fixed_winding, wire_windings
from srmapp.turns import choose_turns
from srmcore.model.design import Design, MeshSettings, RegionMaterials

P = make_8_6()
THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def test_references_registry_and_fixture(srm_8_6, srm_12_8, srm_24_16, reference_design):
    assert srm_8_6 == make_8_6() and srm_12_8 == make_12_8() and srm_24_16 == make_24_16()
    assert REFERENCES["8/6"]() == make_8_6()
    assert REFERENCES["12/8"](turns_per_pole=5).turns_per_pole == 5
    assert set(REFERENCES) == {"8/6", "12/8", "24/16"}
    assert make_24_16().n_stator_poles == 24 and make_12_8().n_phases == 3


def test_fixed_winding_density_mode():
    w = fixed_winding(P, _req(), turns=10, strands=1, paths=2, wire=None, j_peak=8e6)
    area = 0.5 * est.coil_side_area(P) / 10
    assert w.copper_area == pytest.approx(area)
    assert w.current == pytest.approx(8e6 * area * 2)
    assert (w.turns, w.strands, w.paths, w.wire) == (10, 1, 2, None)


def test_fixed_winding_wire_mode():
    req = _req(wires=[THICK], phase_current_a=40.0)
    w = fixed_winding(P, req, turns=2, strands=2, paths=1, wire=0, j_peak=0.0)
    assert w.current == 40.0
    assert w.copper_area == pytest.approx(2 * req.wires[0].copper_area)
    assert w.wire == 0


def test_fixed_winding_equals_a_generated_one():
    req = _req(wires=[THICK], phase_current_a=40.0)
    g = wire_windings(P, req, 0, 1e12)[3]
    assert fixed_winding(P, req, g.turns, g.strands, g.paths, 0, 0.0) == g


@pytest.mark.parametrize("kw, field", [
    (dict(paths=3), "paths"),
    (dict(wire=1, paths=1), "wire"),
    (dict(wire=-1, paths=1), "wire"),
    (dict(strands=1, turns=500, paths=1, wire=0), "turns"),
])
def test_fixed_winding_rejects(kw, field):
    req = _req(wires=[THICK], phase_current_a=40.0)
    args = dict(turns=2, strands=1, paths=1, wire=0, j_peak=0.0) | kw
    with pytest.raises(ValueError, match=field):
        fixed_winding(P, req, **args)


def test_fixed_winding_wire_given_without_wire_mode():
    with pytest.raises(ValueError, match="wire"):
        fixed_winding(P, _req(), turns=5, strands=1, paths=1, wire=0, j_peak=8e6)
    with pytest.raises(ValueError, match="strands"):
        fixed_winding(P, _req(), turns=5, strands=2, paths=1, wire=None, j_peak=8e6)


def test_choose_turns_only_scans_the_given_winding(monkeypatch):
    from types import SimpleNamespace

    import numpy as np
    from srmapp import turns as t
    req = _req()
    w = fixed_winding(P, req, 10, 1, 1, None, 8e6)
    monkeypatch.setattr(t, "_envelope", lambda *a, **k: SimpleNamespace(i_rms=np.array([1.0])))
    monkeypatch.setattr(t, "requirement_ratios", lambda env, req: (1.5, 1.5))
    choice = choose_turns(None, P, req, only=w, margin=1.0)
    assert len(choice.scan) == 1 and choice.scan[0].winding is w and choice.point.winding is w


def test_case_inputs_validation():
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    c = CaseInputs(requirements=_req(), design=design)
    assert c.winding == "auto"
    with pytest.raises(ValidationError):
        CaseInputs(requirements=_req(), design=design, bogus=1)
    with pytest.raises(ValidationError, match="preset"):
        CaseInputs(requirements=_req(), design=Design(machine=make_8_6(), mesh=MeshSettings(preset="reference")))
    for bad in (dict(turns=0), dict(turns=1, strands=0), dict(turns=1, paths=0), dict(turns=1, wire=-1)):
        with pytest.raises(ValidationError):
            FixedWinding(**bad)
    assert CaseInputs(requirements=_req(), design=design, winding=FixedWinding(turns=3)).winding.turns == 3


def test_search_settings_and_reference_design():
    machine = make_8_6(materials=RegionMaterials(stator="10JNEX900", rotor="10JNEX900"))
    c = CaseInputs(requirements=_req(), design=Design(machine=machine, mesh=MeshSettings(preset="screening")),
                   j_limit=3e6, j_peak=9e6)
    s = c.search_settings()
    assert s.preset == "screening" and s.materials == machine.materials
    assert (s.j_limit, s.j_peak, s.margin, s.j_peak_max) == (3e6, 9e6, None, None)
    assert s.resolved_margin == SearchSettings(materials=machine.materials).resolved_margin
    d = reference_design(c)
    assert d.machine.turns_per_pole == REFERENCE_TURNS == 20
    assert d.mesh == c.design.mesh and c.design.machine.turns_per_pole == 60
