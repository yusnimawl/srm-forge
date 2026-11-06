import dataclasses

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.turns import rescale_stack, rescale_turns, restack

PER_DEPTH = ("psi", "torque_arkkio", "torque_virtual_work", "energy", "coenergy", "l_inc", "pole_force")
UNCHANGED = ("angles", "currents", "b_peak", "iterations", "status", "filled")


def _map():
    r = synthetic_map(n_angles=16)
    rng = np.random.default_rng(1)
    return dataclasses.replace(r, l_inc=rng.random(r.l_inc.shape), pole_force=rng.random(r.pole_force.shape))


def test_rescale_stack_multiplies_every_per_depth_quantity_and_keeps_the_field_and_axes():
    r = _map()
    s = rescale_stack(r, 1.7)
    for name in PER_DEPTH:
        np.testing.assert_allclose(getattr(s, name), 1.7 * getattr(r, name), rtol=1e-15)
    for name in UNCHANGED:
        np.testing.assert_array_equal(getattr(s, name), getattr(r, name))
    assert (s.circuits, s.excited, s.complete, s.design_hash, s.preset) == (
        r.circuits, r.excited, r.complete, r.design_hash, r.preset)


@pytest.mark.parametrize("k", [0.0, -1.0, float("nan"), float("inf")])
def test_rescale_stack_rejects_a_ratio_that_is_not_positive_and_finite(k):
    with pytest.raises(ValueError, match="stack ratio"):
        rescale_stack(_map(), k)


def test_stack_and_turn_rescales_compose_in_either_order():
    r = _map()
    a = rescale_turns(rescale_stack(r, 0.6), 2.5)
    b = rescale_stack(rescale_turns(r, 2.5), 0.6)
    for name in PER_DEPTH + ("currents",):
        np.testing.assert_allclose(getattr(a, name), getattr(b, name), rtol=1e-14)


def test_restack_uses_the_ratio_of_the_two_stack_lengths():
    mapped = make_8_6()
    target = make_8_6(stack_length=1.25 * mapped.stack_length)
    r = _map()
    np.testing.assert_allclose(restack(r, mapped, target).psi, 1.25 * r.psi, rtol=1e-14)


@pytest.mark.parametrize("change", [{"air_gap": 5e-4}, {"turns_per_pole": 30}, {"shaft_diameter": 0.025}])
def test_restack_refuses_machines_that_differ_in_more_than_the_stack(change):
    mapped = make_8_6()
    target = make_8_6(stack_length=2 * mapped.stack_length, **change)
    with pytest.raises(ValueError, match="only in stack_length"):
        restack(_map(), mapped, target)


def test_fem_point_at_another_stack_equals_the_rescale():
    """The field does not depend on the stack: the same mesh, the same solution, every per-depth quantity × k."""
    pytest.importorskip("ngsolve")
    from srmcore.maps.point import solve_point
    from srmcore.mesh import build_machine_mesh
    from srmcore.model.design import Design, MeshSettings
    from srmcore.solvers.factory import make_solver

    base = make_8_6()
    long = make_8_6(stack_length=1.6 * base.stack_length)
    designs = [Design(machine=m, mesh=MeshSettings(preset="screening")) for m in (base, long)]
    meshes = [build_machine_mesh(d) for d in designs]
    for part in ("stator", "rotor"):
        np.testing.assert_array_equal(getattr(meshes[0], part).nodes, getattr(meshes[1], part).nodes)
    solver = make_solver("ngsolve", threads=1)
    angle = 0.35 * 2 * np.pi / base.n_rotor_poles         # between aligned and unaligned, so the torque is large
    a, b = (solve_point(s, d, angle, {"A": 20.0}, solver) for s, d in zip(meshes, designs))
    assert a.iterations == b.iterations
    for name in ("psi", "torque_arkkio", "torque_virtual_work", "energy", "coenergy", "pole_force"):
        np.testing.assert_allclose(getattr(b, name), 1.6 * np.asarray(getattr(a, name)), rtol=1e-9,
                                   atol=1e-12 * np.max(np.abs(getattr(b, name))))
    assert b.b_peak == pytest.approx(a.b_peak, rel=1e-12)


@pytest.mark.slow
def test_fem_map_at_another_stack_matches_the_rescale():
    pytest.importorskip("ngsolve")
    from srmcore.maps import build_map
    from srmcore.model.design import Design, MeshSettings

    base = make_8_6()
    short = make_8_6(stack_length=0.55 * base.stack_length)

    def run(machine):
        return build_map(Design(machine=machine, mesh=MeshSettings(preset="screening")), 20.0, n_angles=6,
                         n_currents=4, workers=2)
    predicted, solved = restack(run(base), base, short), run(short)
    for name in ("psi", "torque_arkkio", "energy", "coenergy", "pole_force"):
        scale = np.max(np.abs(getattr(solved, name)))
        np.testing.assert_allclose(getattr(solved, name), getattr(predicted, name), rtol=1e-9, atol=1e-12 * scale)
    np.testing.assert_allclose(solved.b_peak, predicted.b_peak, rtol=1e-12)
