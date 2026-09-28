import pydantic
import pytest

from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import InputError, MeshRejected, ValidationIssue


def test_derived_radii(srm_8_6):
    p = srm_8_6
    assert p.stator_outer_radius == pytest.approx(0.080)
    assert p.rotor_outer_radius == pytest.approx(0.040)
    assert p.bore_radius == pytest.approx(0.0404)
    assert p.shaft_radius == pytest.approx(0.010)
    assert p.stator_yoke_inner_radius == pytest.approx(0.068)
    assert p.rotor_yoke_outer_radius == pytest.approx(0.022)
    assert p.band_inner_radius == pytest.approx(0.040 + 0.0004 / 3)
    assert p.band_outer_radius == pytest.approx(0.040 + 2 * 0.0004 / 3)


def test_design_json_round_trip(srm_8_6):
    design = Design(machine=srm_8_6, mesh=MeshSettings(preset="screening", airgap_radial_layers=5))
    restored = Design.from_json(design.to_json())
    assert restored == design
    assert '"schema_version": 1' in design.to_json()


def test_unknown_field_rejected(srm_8_6):
    data = srm_8_6.model_dump()
    data["stator_od_mm"] = 160
    with pytest.raises(pydantic.ValidationError):
        RadialSRMParams(**data)


def test_wrong_schema_version_rejected(srm_8_6):
    data = srm_8_6.model_dump()
    data["schema_version"] = 2
    with pytest.raises(pydantic.ValidationError):
        RadialSRMParams(**data)


def test_input_error_lists_only_errors_in_message():
    issues = [
        ValidationIssue("air_gap", "positive", "must be > 0"),
        ValidationIssue("stator_pole_arc", "arc_order", "βs > βr", severity="warning"),
    ]
    err = InputError(issues)
    assert isinstance(err, ValueError)
    assert err.issues == issues
    assert "air_gap: [positive]" in str(err)
    assert "stator_pole_arc" not in str(err)


def test_mesh_rejected_carries_report():
    err = MeshRejected(["min angle 3.0° < 10.0°"], report={"n": 1})
    assert err.reasons == ["min angle 3.0° < 10.0°"]
    assert err.report == {"n": 1}
    assert "min angle" in str(err)
