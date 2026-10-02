import math

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import make_8_6, make_12_8, make_24_16
from srmcore.model.design import EdgeRefinement, MeshSettings
from srmcore.model.regions import REGION_SIZE_KEYS
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.mesh.sizing import size_at


def test_screening_preset_defaults(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening"))
    assert r.gap_size == pytest.approx(0.0004 / 4)
    assert r.band_divisions % 24 == 0
    r_mid = (srm_8_6.band_inner_radius + srm_8_6.band_outer_radius) / 2
    pitch_length = r_mid * r.band_pitch
    assert pitch_length <= 3.0 * r.gap_size + 1e-15   # divisions rounded up => pitch not above target
    assert pitch_length > 3.0 * r.gap_size * r.band_divisions / (r.band_divisions + 24)
    assert r.band_pitch == pytest.approx(2 * math.pi / r.band_divisions)
    assert set(r.region_sizes) == set(REGION_SIZE_KEYS)
    assert r.region_sizes["airgap"] == r.gap_size


def test_scale_one_is_identity(srm_8_6):
    for preset in ("screening", "full", "reference"):
        a = resolve_mesh_settings(srm_8_6, MeshSettings(preset=preset))
        assert resolve_mesh_settings(srm_8_6, MeshSettings(preset=preset, scale=1.0)) == a


@pytest.mark.parametrize("preset, scale", [("full", 2 ** -0.5), ("reference", 0.25)])
def test_presets_are_scaled_screening(srm_8_6, preset, scale):
    _assert_same_mesh(resolve_mesh_settings(srm_8_6, MeshSettings(preset=preset)),
                      resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening", scale=scale)))


def test_preset_and_user_scale_multiply(srm_8_6):
    _assert_same_mesh(resolve_mesh_settings(srm_8_6, MeshSettings(preset="full", scale=0.5)),
                      resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening", scale=0.5 * 2 ** -0.5)))


def _assert_same_mesh(a, b):
    """Equal up to floating-point rounding of the scale products."""
    assert a.band_divisions == b.band_divisions
    assert a.gap_size == pytest.approx(b.gap_size, rel=1e-12)
    assert a.region_sizes == pytest.approx(b.region_sizes, rel=1e-12)
    assert a.refinement.keys() == b.refinement.keys()
    for tag, values in a.refinement.items():
        assert values == pytest.approx(b.refinement[tag], rel=1e-12)


def test_scale_half_halves_lengths_and_doubles_divisions(srm_8_6):
    a = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening"))
    b = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening", scale=0.5))
    assert b.gap_size == pytest.approx(a.gap_size / 2)
    assert all(b.region_sizes[k] == pytest.approx(v / 2) for k, v in a.region_sizes.items())
    for tag, (size, g) in a.refinement.items():
        assert b.refinement[tag] == pytest.approx((size / 2, 1 + (g - 1) / 2))
    assert b.band_divisions == 2 * a.band_divisions


@pytest.mark.parametrize("scale", [2 ** -0.5, 0.3, 0.05])
def test_scaled_divisions_stay_multiples_of_the_base(srm_8_6, scale):
    base = math.lcm(srm_8_6.n_stator_poles, 2 * srm_8_6.n_rotor_poles)
    d = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening", scale=scale)).band_divisions
    assert d % base == 0 and d >= base


def test_explicit_divisions_are_not_scaled(srm_8_6):
    s = MeshSettings(preset="screening", scale=0.5, airgap_circumferential_divisions=1000)
    assert resolve_mesh_settings(srm_8_6, s).band_divisions == 1000


def test_scale_must_be_positive():
    with pytest.raises(ValidationError):
        MeshSettings(scale=0)


def test_scale_above_one_is_rejected():
    with pytest.raises(ValidationError):
        MeshSettings(scale=1.5)


def test_preset_scale_leaves_explicit_sizes_exact(srm_8_6):
    s = MeshSettings(preset="full", region_sizes={"stator_iron": 0.002})
    assert resolve_mesh_settings(srm_8_6, s).region_sizes["stator_iron"] == 0.002
    s = MeshSettings(preset="full", scale=0.5, region_sizes={"stator_iron": 0.002})
    assert resolve_mesh_settings(srm_8_6, s).region_sizes["stator_iron"] == pytest.approx(0.001)


def test_presets_are_ordered(srm_8_6):
    s, f, ref = (resolve_mesh_settings(srm_8_6, MeshSettings(preset=k)) for k in ("screening", "full", "reference"))
    assert s.region_sizes["stator_iron"] > f.region_sizes["stator_iron"] > ref.region_sizes["stator_iron"]
    assert s.band_divisions < f.band_divisions < ref.band_divisions


def test_user_overrides(srm_8_6):
    s = MeshSettings(
        preset="screening",
        airgap_radial_layers=6,
        airgap_circumferential_divisions=480,
        region_sizes={"shaft": 0.01},
        refinement={"pole_tip": EdgeRefinement(size=5e-5, growth=1.2)},
    )
    r = resolve_mesh_settings(srm_8_6, s)
    assert r.gap_size == pytest.approx(0.0004 / 6)
    assert r.band_divisions == 480
    assert r.region_sizes["shaft"] == 0.01
    assert r.refinement["pole_tip"] == (5e-5, 1.2)
    assert r.refinement["pole_root"][1] == pytest.approx(1.3)


def test_airgap_region_size_override_propagates_to_gap_and_refinement(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening", region_sizes={"airgap": 5e-5}))
    assert r.gap_size == pytest.approx(5e-5)
    assert r.refinement["pole_tip"][0] == pytest.approx(3.0 * 5e-5)  # screening preset tip_factor
    assert r.band_divisions % 24 == 0
    r_mid = (srm_8_6.band_inner_radius + srm_8_6.band_outer_radius) / 2
    pitch_length = r_mid * r.band_pitch
    assert pitch_length <= 3.0 * r.gap_size + 1e-15


def test_airgap_interface_refinement_is_gap_size(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening"))
    assert r.refinement["airgap_interface"] == (r.gap_size, 1.3)


def test_slot_liner_refinement_is_max_of_liner_and_gap(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings(preset="screening"))
    assert r.refinement["slot_liner"] == (max(srm_8_6.slot_liner_thickness, r.gap_size), 1.3)


def test_slot_liner_refinement_uses_gap_floor_when_liner_is_thinner(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings(region_sizes={"airgap": 0.01}))
    assert r.gap_size > srm_8_6.slot_liner_thickness
    assert r.refinement["slot_liner"][0] == pytest.approx(r.gap_size)


def test_slot_liner_refinement_absent_when_no_liner():
    r = resolve_mesh_settings(make_8_6(slot_liner_thickness=0.0), MeshSettings())
    assert "slot_liner" not in r.refinement


def test_size_at_base_feature_and_growth():
    pts = np.array([[0.0, 0.0]])
    features = [(pts, 0.001, 1.5)]
    assert size_at(0.0, 0.0, 0.01, features) == pytest.approx(0.001)
    assert size_at(0.004, 0.0, 0.01, features) == pytest.approx(0.001 + 0.5 * 0.004)
    assert size_at(1.0, 0.0, 0.01, features) == pytest.approx(0.01)
    assert size_at(1.0, 0.0, 0.01, []) == pytest.approx(0.01)


@pytest.mark.parametrize("factory", [make_8_6, make_12_8, make_24_16])
@pytest.mark.parametrize("preset", ["screening", "full"])
def test_unaligned_position_lands_on_the_band_grid(factory, preset):
    # (pi/Nr)/pitch must be an integer: the unaligned rotor position (half a rotor pitch off the
    # aligned position) must land on the band grid, not just the aligned positions.
    p = factory()
    r = resolve_mesh_settings(p, MeshSettings(preset=preset))
    k = (math.pi / p.n_rotor_poles) / r.band_pitch
    assert k == pytest.approx(round(k), abs=1e-9)
