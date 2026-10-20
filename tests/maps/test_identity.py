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


def test_loss_block_does_not_change_digest():
    import json
    from srmcore.materials import library
    raw = (library._data_dir() / "10JNEX900.json").read_bytes()
    record = json.loads(raw)
    assert "loss" in record
    without = {k: v for k, v in record.items() if k != "loss"}
    assert material_digest(raw) == material_digest(json.dumps(without).encode())
    edited = json.loads(raw)
    edited["loss"]["confidence"] = "A"
    assert material_digest(json.dumps(edited).encode()) == material_digest(raw)


def test_design_hash_ignores_loss_data(monkeypatch):
    import json
    from srmcore.materials import library
    base = design_hash(D)
    real = library._data_dir()
    orig = type(real).read_bytes

    def patched(self):
        data = orig(self)
        if self.name == "10JNEX900.json":
            rec = json.loads(data)
            rec["loss"]["confidence"] = "A"
            return json.dumps(rec).encode()
        return data
    monkeypatch.setattr(type(real), "read_bytes", patched)
    assert design_hash(D) == base
