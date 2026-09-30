import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.api import build_overlap_map
from srmcore.maps.dataset import cached_overlap, overlap_provenance, store_overlap
from srmcore.maps.overlap import OverlapResult, coupling_checks, overlap_window
from srmcore.model.design import Design, MeshSettings

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


def test_window_8_6_is_54_to_60_degrees():
    start, end = overlap_window(make_8_6())
    assert math.degrees(start) == pytest.approx(54.0) and math.degrees(end) == pytest.approx(60.0)


def test_narrow_poles_have_no_overlap():
    assert overlap_window(make_8_6(stator_pole_arc=math.radians(10.0), rotor_pole_arc=math.radians(12.0))) is None


def _synthetic(coupling=0.0, asym=0.0):
    ia = ib = np.array([0.0, 5.0, 10.0])
    shape = (2, 3, 3)
    psi = np.zeros((*shape, 2))
    psi[..., 0] = 0.1 * ia[None, :, None] * (1 + coupling * (ib[None, None, :] > 0))
    psi[..., 1] = 0.1 * ib[None, None, :]
    torque = np.broadcast_to(ia[None, :, None] + ib[None, None, :], shape) * (1 + coupling * (ia[:, None] * ib > 0))
    l_inc = np.zeros((*shape, 2, 2))
    l_inc[..., 0, 0] = l_inc[..., 1, 1] = 0.1
    l_inc[..., 0, 1], l_inc[..., 1, 0] = 0.01, 0.01 * (1 + asym)
    return OverlapResult(np.array([0.94, 1.0]), ia, ib, ("A", "B", "C", "D")[:2], psi, np.array(torque), l_inc,
                         np.zeros(shape, dtype=np.int8), True)


def test_checks_pass_without_coupling():
    checks = {c.name: c for c in coupling_checks(_synthetic())}
    assert [c.status for c in checks.values()] == ["pass"] * 3


def test_coupling_warns_and_asymmetry_fails():
    checks = {c.name: c for c in coupling_checks(_synthetic(coupling=0.5))}
    assert checks["coupling_psi"].status == "warn" and checks["coupling_torque"].status == "warn"
    assert checks["coupling_psi"].value == pytest.approx(0.5 / 1.5) and checks["coupling_torque"].value == pytest.approx(1 / 3)
    assert coupling_checks(_synthetic(asym=0.5))[2].status == "fail"


def test_cache_roundtrip(tmp_path):
    from srmcore.solvers.factory import make_solver
    r = _synthetic()
    prov = overlap_provenance(DESIGN, r.angles, r.currents_a, r.currents_b, make_solver("skfem_reference"))
    store_overlap(tmp_path, r, prov)
    hit = cached_overlap(tmp_path, prov)
    assert np.array_equal(hit.psi, r.psi) and np.array_equal(hit.l_inc, r.l_inc) and hit.complete
    assert list(tmp_path.glob("overlap_*.h5"))


def test_empty_window_returns_none():
    d = Design(machine=make_8_6(stator_pole_arc=math.radians(10.0), rotor_pole_arc=math.radians(12.0)),
               mesh=MeshSettings(preset="screening"))
    assert build_overlap_map(d, 10.0, solver="skfem_reference") is None


@pytest.mark.slow
def test_fem_overlap_reciprocity_and_coupling():
    pytest.importorskip("ngsolve")
    r = build_overlap_map(DESIGN, 20.0, workers=4, n_angles=2, n_currents=3)
    assert r.complete and r.psi.shape == (2, 3, 3, 4) and r.l_inc.shape == (2, 3, 3, 2, 2)
    checks = {c.name: c for c in coupling_checks(r)}
    assert checks["reciprocity"].status == "pass"
    # ib = 0 column equals a single-phase solve
    from srmcore.maps.point import solve_point
    from srmcore.mesh import build_machine_mesh
    from srmcore.solvers.factory import make_solver
    p = solve_point(build_machine_mesh(DESIGN), DESIGN, float(r.angles[0]), {"A": float(r.currents_a[2])},
                    make_solver("ngsolve"))
    assert r.psi[0, 2, 0, 0] == pytest.approx(p.psi[0], rel=1e-9)


def test_nonconverged_point_fails_the_map(monkeypatch):
    from srmcore.maps import overlap
    from srmcore.model.errors import MapFailed
    row = {"psi": np.zeros(4), "torque_arkkio": 0.0, "status": 2, "l_inc": np.zeros((4, 4)),
           "circuits": ("A", "B", "C", "D")}
    monkeypatch.setattr(overlap, "map_ordered", lambda *a, **k: [row] * 4)
    with pytest.raises(MapFailed):
        overlap.run_overlap_map(None, DESIGN, np.array([0.9, 1.0]), np.array([0.0, 1.0]), np.array([0.0]),
                                solver_name="skfem_reference")


def test_incomplete_and_nonzero_start_and_nonfinite():
    r = _synthetic()
    with pytest.raises(ValueError, match="incomplete"):
        coupling_checks(dataclasses.replace(r, complete=False))
    with pytest.raises(ValueError, match="start at 0"):
        coupling_checks(dataclasses.replace(r, currents_a=r.currents_a + 1))
    bad = r.l_inc.copy()
    bad[0, 1, 1, 0, 1] = np.nan
    c = {c.name: c for c in coupling_checks(dataclasses.replace(r, l_inc=bad))}
    assert c["reciprocity"].status == "fail" and "non-finite" in c["reciprocity"].detail


def test_cancelled_overlap_is_incomplete_and_not_cached(tmp_path):
    r = build_overlap_map(DESIGN, 10.0, solver="skfem_reference", n_angles=2, n_currents=2, workers=1,
                          cache_dir=tmp_path, cancel=lambda: True)
    assert not r.complete and np.all(r.status == -1) and np.isnan(r.psi).all()
    assert not list(tmp_path.glob("overlap_*.h5"))
