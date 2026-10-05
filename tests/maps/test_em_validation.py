"""em_validate and its parts (spec docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md)."""
import dataclasses
import math
from importlib.metadata import version

import numpy as np
import pytest

from conftest import make_8_6
from map_fixtures import synthetic_map
from srmcore.maps import validation as V
from srmcore.maps.checks import Check
from srmcore.maps.end_winding import end_winding_inductance
from srmcore.maps.results import key_numbers
from srmcore.maps.validation import KEYS, KeyPoint, js_laws, key_points
from srmcore.materials.laws import library_law
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.model.errors import InputError

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))


def test_key_points_follow_the_key_numbers():
    r = synthetic_map(n_angles=16)
    pts = {p.key: p for p in key_points(r, DESIGN.machine)}
    assert tuple(pts) == KEYS
    i_max = r.currents[-1]
    tau = 2 * math.pi / DESIGN.machine.n_rotor_poles
    assert pts["la"] == KeyPoint("la", 0.0, 0.05 * i_max)
    assert pts["lu"].angle == pytest.approx(tau / 2) and pts["lu"].current == pytest.approx(0.05 * i_max)
    assert pts["psi_max"] == KeyPoint("psi_max", 0.0, i_max)
    a, i = np.unravel_index(np.argmax(np.abs(r.torque_arkkio)), r.torque_arkkio.shape)
    assert pts["peak_torque"] == KeyPoint("peak_torque", float(r.angles[a]), float(r.currents[i]))


def test_js_laws_scale_both_iron_materials():
    d = DESIGN.model_copy(update={"machine": DESIGN.machine.model_copy(
        update={"materials": RegionMaterials(stator="M19", rotor="steel_1010")})})
    laws = js_laws(d, 1.02)
    for name in ("M19", "steel_1010"):
        base = library_law(name)
        assert laws[id(base)].js == pytest.approx(1.02 * base.js)
        assert laws[id(base)].bn == pytest.approx(base.bn)


def test_js_minus_two_percent_is_forbidden_by_the_m19_data():
    with pytest.raises(InputError):
        js_laws(DESIGN, 0.98)


def _map():
    return synthetic_map(n_angles=16)


# The fake solves return the map's own peak torque, as a solve on the design's mesh would.
GOOD = {"la": 0.03, "lu": 0.004, "peak_torque": float(np.max(np.abs(_map().torque_arkkio))), "psi_max": 0.3}


def _patch(monkeypatch, *, ref_scale=1.0, minus_ok=True, nan_key=None, fem_status="pass", versions=(),
           torque_scale=1.0):
    def fake_values(static, design, points, excited, solver, js_factor=1.0):
        if js_factor < 1 and not minus_ok:
            raise InputError([])
        v = {k: x * (1 + 0.01 * (js_factor - 1) / V.JS_STEP) for k, x in GOOD.items()}
        if js_factor == 1.0:
            v["peak_torque"] *= torque_scale
        if static == "reference":
            v = {k: x * (ref_scale[k] if isinstance(ref_scale, dict) else ref_scale) for k, x in v.items()}
        if nan_key and static == "full":
            v[nan_key] = float("nan")
        return v
    monkeypatch.setattr(V, "point_values", fake_values)
    monkeypatch.setattr(V, "build_machine_mesh", lambda d: d.mesh.preset)
    monkeypatch.setattr(V, "make_solver", lambda name, threads=None: None)
    monkeypatch.setattr(V, "fem_checks", lambda d, r, solver, workers: (
        () if d.mesh.preset == "screening" else (Check("held_out_psi", fem_status, 0.0, 0.005, ""),)))
    monkeypatch.setattr(V, "VALIDATED_VERSIONS", versions)


def test_label_awarded_only_when_every_check_passes(monkeypatch):
    _patch(monkeypatch, versions=(version("srmcore"),))
    v = V.em_validate(DESIGN, _map())
    assert v.label == V.LABEL and all(c.status == "pass" for c in v.checks)
    assert v.material_grades == {"stator": "C", "rotor": "C"}


def test_unvalidated_engine_version_blocks_the_label(monkeypatch):
    _patch(monkeypatch)
    v = V.em_validate(DESIGN, _map())
    assert v.label is None
    assert {c.name for c in v.checks if c.status != "pass"} == {"engine_version"}


def test_screening_map_is_never_labelled(monkeypatch):
    _patch(monkeypatch, versions=(version("srmcore"),))
    d = DESIGN.model_copy(update={"mesh": MeshSettings(preset="screening")})
    v = V.em_validate(d, _map())
    failed = {c.name for c in v.checks if c.status != "pass"}
    assert v.label is None and {"preset", "fem_checks"} <= failed


def test_filled_point_blocks_the_label(monkeypatch):
    _patch(monkeypatch)
    r = _map()
    filled = r.filled.copy()
    filled[3, 2] = True
    v = V.em_validate(DESIGN, dataclasses.replace(r, filled=filled))
    assert {c.name: c.status for c in v.checks}["no_filled_points"] == "fail"


def _to_corrected(v):
    """2D value / end-corrected value per key: the factor that moves a 2D-relative spread to the budget basis."""
    return {k: v.budget.values_2d[k] / v.budget.values[k] for k in KEYS}


def test_mesh_difference_beyond_tolerance_fails_and_enters_the_budget(monkeypatch):
    _patch(monkeypatch, ref_scale=1.01)
    v = V.em_validate(DESIGN, _map())
    status = {c.name: c.status for c in v.checks}
    assert status["point_convergence_psi"] == "fail" and status["point_convergence_torque"] == "pass"
    mesh = next(r for r in v.budget.rows if r.source == "mesh")
    assert mesh.rel["la"] == pytest.approx(0.01 / 1.01 * _to_corrected(v)["la"])


def test_failing_psi_check_names_the_worst_key(monkeypatch):
    _patch(monkeypatch, ref_scale={"la": 1.0, "lu": 1.02, "peak_torque": 1.0, "psi_max": 1.01})
    c = {c.name: c for c in V.em_validate(DESIGN, _map()).checks}["point_convergence_psi"]
    assert c.status == "fail" and "worst at lu" in c.detail


def test_nonconverged_psi_key_is_named(monkeypatch):
    _patch(monkeypatch, nan_key="la")
    v = V.em_validate(DESIGN, _map())
    c = {c.name: c for c in v.checks}["point_convergence_psi"]
    assert c.status == "fail" and "la key-point solve non-converged" in c.detail and "full" in c.detail
    material = next(row for row in v.budget.rows if row.source == "material")
    assert "non-converged Js solve at la" in material.note


def test_nonconverged_key_point_fails_its_check(monkeypatch):
    _patch(monkeypatch, nan_key="peak_torque")
    c = {c.name: c for c in V.em_validate(DESIGN, _map()).checks}["point_convergence_torque"]
    assert c.status == "fail" and "non-finite" in c.detail


def test_budget_rows_sum_and_use_the_corrected_values(monkeypatch):
    _patch(monkeypatch)
    r = _map()
    v = V.em_validate(DESIGN, r)
    b = v.budget
    assert [row.source for row in b.rows] == ["mesh", "material", "end_effect", "digitisation"]
    for k in V.KEYS:
        assert b.total[k] == pytest.approx(sum(row.rel[k] for row in b.rows))
    key = key_numbers(r, DESIGN.machine)
    l1, l2 = (end_winding_inductance(DESIGN.machine, f) for f in V.END_WINDING_IMAGE)
    assert b.values_2d["la"] == key.la
    assert b.values["la"] == pytest.approx(key.la + (l1 + l2) / 2)
    assert b.values["peak_torque"] == key.peak_torque
    material = next(row for row in b.rows if row.source == "material")
    scale = _to_corrected(v)
    assert scale["la"] < 1 and scale["peak_torque"] == 1.0
    # Js ±2 % gives ±1 % in the fake; the relative spread is rescaled from the 2D to the corrected value
    assert material.rel["la"] == pytest.approx((0.01 + V.GRADE_ALLOWANCE["C"]) * scale["la"])
    assert material.rel["peak_torque"] == pytest.approx(0.01 + V.GRADE_ALLOWANCE["C"])
    end =next(row for row in b.rows if row.source == "end_effect")
    assert end.rel["peak_torque"] == 0.0 and end.rel["la"] == pytest.approx((l2 - l1) / 2 / b.values["la"])


def test_js_minus_forbidden_uses_plus_only(monkeypatch):
    _patch(monkeypatch, minus_ok=False)
    v = V.em_validate(DESIGN, _map())
    material = next(row for row in v.budget.rows if row.source == "material")
    assert material.rel["la"] == pytest.approx((0.01 + V.GRADE_ALLOWANCE["C"]) * _to_corrected(v)["la"])
    assert "+2 % only" in material.note


def test_worse_grade_sets_the_allowance(monkeypatch):
    real = V.load_material

    def graded(name):
        m = real(name)
        return m.model_copy(update={"confidence": "B"}) if name == "steel_1010" else m
    monkeypatch.setattr(V, "load_material", graded)
    _patch(monkeypatch)
    d = DESIGN.model_copy(update={"machine": DESIGN.machine.model_copy(
        update={"materials": RegionMaterials(stator="steel_1010", rotor="M19")})})
    v = V.em_validate(d, _map())
    assert v.material_grades == {"stator": "B", "rotor": "C"}
    material = next(row for row in v.budget.rows if row.source == "material")
    assert material.rel["la"] == pytest.approx((0.01 + V.GRADE_ALLOWANCE["C"]) * _to_corrected(v)["la"])


def test_map_of_another_design_blocks_the_label(monkeypatch):
    _patch(monkeypatch, versions=(version("srmcore"),))
    assert {c.name: c.status for c in V.em_validate(DESIGN, _map()).checks}["map_matches_design"] == "pass"
    _patch(monkeypatch, versions=(version("srmcore"),), torque_scale=1.01)
    v = V.em_validate(DESIGN, _map())
    assert v.label is None and {c.name: c.status for c in v.checks}["map_matches_design"] == "fail"


def test_nonconverged_peak_torque_solve_fails_the_map_match(monkeypatch):
    _patch(monkeypatch, nan_key="peak_torque")
    c = {c.name: c for c in V.em_validate(DESIGN, _map()).checks}["map_matches_design"]
    assert c.status == "fail" and "non-finite" in c.detail


def test_nan_budget_blocks_the_label(monkeypatch):
    _patch(monkeypatch, versions=(version("srmcore"),), nan_key="la")
    v = V.em_validate(DESIGN, _map())
    c = {c.name: c for c in v.checks}["budget_finite"]
    assert v.label is None and c.status == "fail" and "la" in c.detail


def test_budget_finite_passes_on_a_clean_budget(monkeypatch):
    _patch(monkeypatch)
    assert {c.name: c.status for c in V.em_validate(DESIGN, _map()).checks}["budget_finite"] == "pass"


def test_engine_version_is_the_installed_package_version():
    import srmcore
    assert srmcore.__version__ == version("srmcore")


@pytest.mark.slow
def test_em_validate_end_to_end_on_the_8_6_full_mesh(tmp_path):
    pytest.importorskip("ngsolve")
    from srmcore.maps import build_map, em_validate
    r = build_map(DESIGN, 20.0, n_angles=16, n_currents=6, cache_dir=tmp_path)
    v = em_validate(DESIGN, r)
    status = {c.name: c.status for c in v.checks}
    assert v.label is None and status["engine_version"] == "fail"
    # held_out_* and band_radius are not asserted: the 16 x 6 grid is too coarse for the held-out limits; the
    # example runs the default grid.
    for name in ("preset", "no_filled_points", "map_matches_design", "point_convergence_psi",
                 "point_convergence_torque", "material_grade", "budget_finite"):
        assert status[name] == "pass", name
    assert {"held_out_psi", "held_out_torque", "band_radius"} <= set(status)
    for k in ("la", "lu", "peak_torque", "psi_max"):
        assert 0 < v.budget.total[k] < 0.5 and np.isfinite(v.budget.values[k])
    assert "+2 % only" in next(row for row in v.budget.rows if row.source == "material").note
