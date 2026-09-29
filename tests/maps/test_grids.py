import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.grids import GRID_SIZES, angle_grid, current_grid
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


def test_angle_grid_is_denser_near_alignment():
    a = angle_grid(MACHINE, _divisions("full"), 30)
    gaps = np.diff(a)
    assert gaps[:2].mean() <= gaps[len(gaps) // 2 - 1: len(gaps) // 2 + 1].mean()


def test_tiny_grid_and_coarse_band_pitch_drop_duplicates_but_keep_zero():
    a = angle_grid(MACHINE, band_divisions=MACHINE.n_rotor_poles * 2, n=30)   # 2 band steps per pole pitch
    assert list(a) == pytest.approx([0.0, TAU_R / 2])
    assert list(angle_grid(MACHINE, _divisions("screening"), 1)) == [0.0]


def test_current_grid_starts_at_zero_ends_at_i_max_and_is_denser_at_low_current():
    c = current_grid(20.0, 8)
    assert c[0] == 0.0 and c[-1] == 20.0 and np.all(np.diff(c) > 0)
    assert np.diff(c)[0] < np.diff(c)[-1]
