import math

import pytest

pytest.importorskip("fastapi")

from conftest import make_8_6
from srmapp.case import CaseInputs
from srmapp.requirements import Requirements
from srmcore.model.design import Design, MeshSettings
from srmweb import cases
from srmweb.setup import setup_loc
from srmweb.store import Store

SMALL = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)


def _raw(**over) -> dict:
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    return CaseInputs(requirements=Requirements(**SMALL), design=design).model_dump(mode="json") | over


def test_check_case_accepts_valid_inputs():
    inputs, errors, warnings = cases.check_case(_raw())
    assert isinstance(inputs, CaseInputs) and errors == [] and warnings == []


@pytest.mark.parametrize("winding, field", [({}, "turns"), ({"turns": 0}, "turns"), ({"strands": 0, "turns": 5}, "strands")])
def test_fixed_winding_errors_sit_at_the_field(winding, field):
    inputs, errors, _ = cases.check_case(_raw(winding=winding))
    assert inputs is None and [e["loc"] for e in errors] == [["winding", field]]


def test_a_misspelt_winding_keeps_both_branch_errors():
    _, errors, _ = cases.check_case(_raw(winding="manual"))
    assert errors and all(e["loc"][0] == "winding" for e in errors)


def test_rules_after_parsing_carry_their_locs():
    _, errors, warnings = cases.check_case(_raw(winding={"turns": 10, "paths": 3}))
    assert [e["loc"] for e in errors] == [["winding", "paths"]]
    _, errors, warnings = cases.check_case(_raw() | {"design": {**_raw()["design"], "machine": {
        **_raw()["design"]["machine"], "stator_pole_arc": math.radians(40)}}})
    assert [e["loc"] for e in errors] == [["design", "machine", "rotor_pole_arc"]]
    assert [w["loc"] for w in warnings] == [["design", "machine", "stator_pole_arc"]]


def test_density_fixed_winding_over_the_current_limit_is_a_turns_error():
    _, errors, _ = cases.check_case(_raw(winding={"turns": 10}) | {"requirements": {**_raw()["requirements"], "phase_current_a": 1.0}})
    assert [e["loc"] for e in errors] == [["winding", "turns"]]


def test_resolved_margin():
    assert cases.resolved_margin(_raw()) > 1
    assert cases.resolved_margin(_raw(margin=1.3)) == 1.3
    assert cases.resolved_margin({"design": {}}) is None
    machine = _raw()["design"]["machine"] | {"materials": {"stator": "copper", "rotor": "10JNEX900"}}
    assert cases.resolved_margin(_raw() | {"design": {**_raw()["design"], "machine": machine}}) is None


def test_setup_loc_maps_inputs_locs_to_the_setup_file():
    assert setup_loc(["design", "machine", "materials", "stator"]) == ["materials", "stator"]
    assert setup_loc(["design", "machine", "air_gap"]) == ["geometry", "machine", "air_gap"]
    assert setup_loc(["winding", "turns"]) == ["winding", "fixed", "turns"]
    assert setup_loc(["requirements", "bus_voltage_v"]) == ["requirements", "bus_voltage_v"]


def test_estimate_adds_the_scan_to_a_new_map(tmp_path, monkeypatch):
    store = Store(tmp_path / "a.db")
    inputs = CaseInputs.model_validate(_raw())
    fixed = CaseInputs.model_validate(_raw(winding={"turns": 10}))
    monkeypatch.setattr(cases, "map_cache_hit", lambda i, d: False)
    assert cases.estimate(inputs, store, tmp_path) == {"new_map": True, "seconds": 228.0 + 450.0, "basis": "budget"}
    assert cases.estimate(fixed, store, tmp_path)["seconds"] == 228.0 + 15.0
    store.add_map_time("screening", 100.0)
    store.add_scan_time("auto", 20.0)
    assert cases.estimate(inputs, store, tmp_path) == {"new_map": True, "seconds": 120.0, "basis": "history"}
    assert cases.estimate(fixed, store, tmp_path)["basis"] == "budget"     # no fixed-winding history
    monkeypatch.setattr(cases, "map_cache_hit", lambda i, d: True)
    assert cases.estimate(inputs, store, tmp_path) == {"new_map": False, "seconds": 20.0, "basis": "history"}
