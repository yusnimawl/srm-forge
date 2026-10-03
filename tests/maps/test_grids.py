import math

import numpy as np
import pytest

from conftest import make_8_6, make_12_8
from srmcore.maps.grids import GRID_SIZES, LA_CURRENT_FRACTION, aligned_angle, angle_grid, current_grid
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import MeshSettings

MACHINE = make_8_6()
TAU_R = 2 * math.pi / MACHINE.n_rotor_poles


def _divisions(preset):
    return resolve_mesh_settings(MACHINE, MeshSettings(preset=preset)).band_divisions


@pytest.mark.parametrize("preset", ["screening", "full"])
def test_angle_grid_is_sorted_on_the_band_grid_inside_one_pole_pitch(preset):
    divisions, n = _divisions(preset), GRID_SIZES[preset][0]
    a = angle_grid(MACHINE, divisions, n)
    pitch = 2 * math.pi / divisions
    assert a[0] == 0.0 and np.all(np.diff(a) > 0) and a[-1] < TAU_R - 1e-9
    assert len(a) <= n
    assert np.allclose(a / pitch, np.round(a / pitch), atol=1e-9)


def test_angle_grid_is_denser_near_the_pole_corners():
    a = angle_grid(MACHINE, _divisions("full"), 48)
    theta_c = (MACHINE.stator_pole_arc + MACHINE.rotor_pole_arc) / 2
    near = np.flatnonzero(np.abs(a - theta_c) <= math.radians(1.5))
    assert len(near) >= 2
    near_gaps = np.diff(a)[near[0]:near[-1]]
    assert near_gaps.min() < 0.5 * np.diff(a).mean()


def test_tiny_grid_and_coarse_band_pitch_drop_duplicates_but_keep_zero():
    a = angle_grid(MACHINE, band_divisions=MACHINE.n_rotor_poles * 2, n=30)   # 2 band steps per pole pitch
    assert list(a) == pytest.approx([0.0, TAU_R / 2])
    assert list(angle_grid(MACHINE, _divisions("screening"), 1)) == [0.0]


def test_current_grid_starts_at_zero_ends_at_i_max_and_is_denser_at_low_current():
    c = current_grid(20.0, 8)
    assert c[0] == 0.0 and c[-1] == 20.0 and np.all(np.diff(c) > 0)
    assert np.diff(c)[0] < np.diff(c)[-1]


def test_current_grid_contains_the_la_current_once():
    c = current_grid(20.0, 8)
    assert len(c) == 9 and np.all(np.diff(c) > 0)
    assert np.isclose(c, LA_CURRENT_FRACTION * 20.0, rtol=0, atol=1e-12).sum() == 1


def test_current_grid_no_duplicate_when_la_current_is_a_node():
    c = current_grid(20.0, 2, exponent=1.0)   # nodes 0, 20; then add 1.0
    assert list(c) == [0.0, 1.0, 20.0]
    c2 = current_grid(1.0, 21, exponent=1.0)  # 0.05 is already a node
    assert len(c2) == 21 and np.all(np.diff(c2) > 0)


@pytest.mark.parametrize("excited, k", [("B", 1), ("C", 2), ("D", 3)])
def test_shifted_angle_grid_contains_the_aligned_angle(excited, k):
    divisions = _divisions("screening")
    aligned = aligned_angle(MACHINE, excited)
    a = angle_grid(MACHINE, divisions, 8, aligned=aligned)
    pitch = 2 * math.pi / divisions
    assert a[0] >= 0 and a[-1] < TAU_R - 1e-9 and np.all(np.diff(a) > 0)
    assert np.isclose(a, aligned, atol=1e-9).any()
    assert np.allclose(a / pitch, np.round(a / pitch), atol=1e-9)
    assert len(a) == len(angle_grid(MACHINE, divisions, 8))


def test_aligned_angles_of_every_phase():
    deg = lambda m, phases: [math.degrees(aligned_angle(m, p)) for p in phases]
    assert deg(MACHINE, "ABCD") == pytest.approx([0, 15, 30, 45])
    assert deg(make_12_8(), "ABC") == pytest.approx([0, 15, 30])
    assert deg(make_8_6(n_stator_poles=6, n_rotor_poles=4, n_phases=3), "ABC") == pytest.approx([0, 30, 60])
