import math

import numpy as np
import pytest
from conftest import make_8_6

from srmapp.field import _static, cached_frame, field_frame, field_mesh, rotated_nodes
from srmcore.maps.point import solve_point
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
SOLVER = "skfem_reference"


def _boom(*a, **k):
    raise AssertionError("must come from the cache")


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("field_cache")


@pytest.fixture(scope="module")
def mesh(cache):
    return field_mesh(DESIGN, solver=SOLVER, cache_dir=cache)


def test_frame_matches_solve_point(cache):
    theta = math.radians(10.0)
    f = field_frame(DESIGN, theta, 5.0, solver=SOLVER, cache_dir=cache)
    p = solve_point(build_machine_mesh(DESIGN), DESIGN, theta, {"A": 5.0}, SkfemReference())
    assert f.psi == pytest.approx(p.psi[0], rel=1e-9) and f.torque == pytest.approx(p.torque_arkkio, rel=1e-9)
    assert f.status == "OK"


def test_band_and_static_triangles_are_the_mesh(cache, mesh):
    theta = math.radians(10.0)
    f = field_frame(DESIGN, theta, 5.0, solver=SOLVER, cache_dir=cache)
    mm = mesh_at_angle(build_machine_mesh(DESIGN), theta)
    assert np.array_equal(np.vstack([mesh.triangles, f.band]), mm.triangles)
    assert f.b.shape == (len(mm.triangles),) and f.a.shape == (len(mm.nodes),)


def test_rotating_the_rotor_nodes_reproduces_the_mesh_nodes(mesh):
    theta = math.radians(10.0)
    mm = mesh_at_angle(build_machine_mesh(DESIGN), theta)
    np.testing.assert_allclose(rotated_nodes(mesh, theta), mm.nodes, atol=1e-12)


def test_frames_and_mesh_come_from_the_cache_on_repeat(cache, monkeypatch):
    first = field_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache)
    monkeypatch.setattr("srmapp.field.solve_point", _boom)
    monkeypatch.setattr("srmapp.field.build_machine_mesh", _boom)
    again = field_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache)
    assert np.array_equal(first.b, again.b) and again.psi == first.psi
    assert cached_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache).torque == first.torque
    assert cached_frame(DESIGN, 0.31, 4.0, solver=SOLVER, cache_dir=cache) is None
    _static.cache_clear()
    field_mesh(DESIGN, solver=SOLVER, cache_dir=cache)          # served from disk


def test_probe_zones(mesh, cache):
    m = DESIGN.machine
    zones = [set(mesh.probes[z]) for z in ("stator_pole", "stator_yoke", "rotor_pole")]
    assert all(zones) and not (zones[0] & zones[1]) and not (zones[0] & zones[2])
    aligned = field_frame(DESIGN, 0.0, 5.0, solver=SOLVER, cache_dir=cache)
    unaligned = field_frame(DESIGN, math.pi / m.n_rotor_poles, 5.0, solver=SOLVER, cache_dir=cache)
    for z in ("stator_pole", "rotor_pole"):
        assert aligned.probes[z] > 2 * unaligned.probes[z], z


def test_cache_key_ignores_numeric_type(cache):
    field_frame(DESIGN, np.float64(0.3), 4, solver=SOLVER, cache_dir=cache)
    f = cached_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache)
    assert f is not None and type(f.angle) is float
