import math

import numpy as np
import pytest

from srmcore.model.design import EdgeRefinement, MeshSettings
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.mesh.sizing import size_at


def test_full_preset_defaults(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings())
    assert r.gap_size == pytest.approx(0.0004 / 4)
    assert r.band_divisions % 24 == 0
    r_mid = (srm_8_6.band_inner_radius + srm_8_6.band_outer_radius) / 2
    pitch_length = r_mid * r.band_pitch
    assert pitch_length <= 1.5 * r.gap_size + 1e-15   # divisions rounded up => pitch not above target
    assert pitch_length > 1.5 * r.gap_size * r.band_divisions / (r.band_divisions + 24)
    assert r.band_pitch == pytest.approx(2 * math.pi / r.band_divisions)
    assert set(r.region_sizes) == {"stator_iron", "rotor_iron", "shaft", "coil", "slot_air", "airgap"}
    assert r.region_sizes["airgap"] == r.gap_size


def test_presets_are_ordered(srm_8_6):
    s, f, ref = (resolve_mesh_settings(srm_8_6, MeshSettings(preset=k)) for k in ("screening", "full", "reference"))
    assert s.region_sizes["stator_iron"] > f.region_sizes["stator_iron"] > ref.region_sizes["stator_iron"]
    assert s.band_divisions < f.band_divisions < ref.band_divisions


def test_user_overrides(srm_8_6):
    s = MeshSettings(
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
    r = resolve_mesh_settings(srm_8_6, MeshSettings(region_sizes={"airgap": 5e-5}))
    assert r.gap_size == pytest.approx(5e-5)
    assert r.refinement["pole_tip"][0] == pytest.approx(2.0 * 5e-5)  # full preset tip_factor
    assert r.band_divisions % 24 == 0
    r_mid = (srm_8_6.band_inner_radius + srm_8_6.band_outer_radius) / 2
    pitch_length = r_mid * r.band_pitch
    assert pitch_length <= 1.5 * r.gap_size + 1e-15


def test_size_at_base_feature_and_growth():
    pts = np.array([[0.0, 0.0]])
    features = [(pts, 0.001, 1.5)]
    assert size_at(0.0, 0.0, 0.01, features) == pytest.approx(0.001)
    assert size_at(0.004, 0.0, 0.01, features) == pytest.approx(0.001 + 0.5 * 0.004)
    assert size_at(1.0, 0.0, 0.01, features) == pytest.approx(0.01)
    assert size_at(1.0, 0.0, 0.01, []) == pytest.approx(0.01)
