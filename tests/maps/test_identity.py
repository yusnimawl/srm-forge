from conftest import make_8_6
from srmcore.maps.identity import design_hash, material_digest
from srmcore.model.design import Design, MeshSettings, RegionMaterials

D = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))


def test_material_digest_ignores_line_endings():
    lf = b'{\n  "a": 1,\n  "b": [1, 2]\n}\n'
    assert material_digest(lf) == material_digest(lf.replace(b"\n", b"\r\n"))
    assert material_digest(lf) != material_digest(b'{"a": 2, "b": [1, 2]}')


def test_design_hash_is_stable_and_short():
    assert design_hash(D) == design_hash(Design.model_validate_json(D.to_json()))
    assert len(design_hash(D)) == 16


def test_design_hash_changes_with_geometry_preset_and_material():
    base = design_hash(D)
    assert design_hash(D.model_copy(update={"machine": D.machine.model_copy(update={"air_gap": 0.00041})})) != base
    assert design_hash(D.model_copy(update={"mesh": MeshSettings(preset="screening")})) != base
    other = D.machine.model_copy(update={"materials": RegionMaterials(stator="M43", rotor="M43")})
    assert design_hash(D.model_copy(update={"machine": other})) != base
