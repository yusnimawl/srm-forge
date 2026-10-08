import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from srmapp.case import LIMIT_FIELDS, CaseInputs
from srmweb.setup import SetupFile, case_inputs_from_setup, setup_from_case
from web_support import REQ, make_client

WIRE = {"kind": "round", "diameter": 1e-3, "outer_diameter": 1.1e-3}


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c


def _reference(client, requirements=REQ):
    r = client.post("/api/cases", json={"origin": "reference", "name": "8/6", "requirements": requirements,
                                        "preset": "screening"})
    assert r.status_code == 201, r.text
    return r.json()


def _setup(client, **inputs_over):
    case = _reference(client)
    if inputs_over:
        r = client.patch(f"/api/cases/{case['id']}", json={"inputs": case["inputs"] | inputs_over})
        assert r.status_code == 200, r.text
    return case, client.get(f"/api/cases/{case['id']}/setup")


def test_setup_export_and_round_trip(client):
    fixed = {"turns": 20, "strands": 1, "paths": 1}
    limits = dict(zip(LIMIT_FIELDS, (1.2, 1.2e7, 5e6, 2.4e7)))
    case, r = _setup(client, winding=fixed, **limits)
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == 'attachment; filename="8-6 reference.srm-setup.json"'
    body = r.json()
    assert body["schema"] == "srm-setup" and body["version"] == 1 and "search" not in body
    assert "materials" not in body["geometry"]["machine"] and body["materials"]["stator"] == "10JNEX900"
    assert body["winding"] == {"mode": "fixed", "fixed": fixed | {"wire": None}} | limits
    assert body["drive"] == {"bus_voltage_v": 400.0, "phase_current_a": None}
    assert body["geometry"]["preset"] == "screening"
    inputs = CaseInputs.model_validate(client.get(f"/api/cases/{case['id']}").json()["inputs"])
    assert case_inputs_from_setup(SetupFile.model_validate(body)) == inputs
    assert setup_from_case(inputs, "x").model_dump(by_alias=True)["schema"] == "srm-setup"


def test_wire_mode_fixed_winding_round_trip(client):
    wired = REQ | {"wires": [WIRE], "phase_current_a": 30.0}
    case = _reference(client, wired)
    patch = {"inputs": case["inputs"] | {"winding": {"turns": 10, "strands": 1, "paths": 1, "wire": 0}}}
    assert client.patch(f"/api/cases/{case['id']}", json=patch).status_code == 200
    r = client.get(f"/api/cases/{case['id']}/setup")
    assert r.status_code == 200, r.text
    assert r.json()["winding"]["fixed"]["wire"] == 0 and r.json()["drive"]["phase_current_a"] == 30.0
    inputs = CaseInputs.model_validate(client.get(f"/api/cases/{case['id']}").json()["inputs"])
    assert case_inputs_from_setup(SetupFile.model_validate(r.json())) == inputs
    imported = client.post("/api/cases", json={"origin": "import", "setup": r.json()})
    assert imported.status_code == 201, imported.text
    assert imported.json()["inputs"] == client.get(f"/api/cases/{case['id']}").json()["inputs"]


def test_import_creates_a_stale_draft(client):
    _, r = _setup(client)
    imported = client.post("/api/cases", json={"origin": "import", "setup": r.json()})
    assert imported.status_code == 201, imported.text
    case = imported.json()
    assert case["origin"] == "import" and case["stale"] and case["label"] == "imported setup"
    assert case["poles"] == "8/6" and case["inputs"]["design"]["machine"]["materials"]["stator"] == "10JNEX900"


def test_drive_overrides_requirements(client):
    _, r = _setup(client)
    setup = r.json() | {"drive": {"bus_voltage_v": 300.0, "phase_current_a": 25.0}}
    case = client.post("/api/cases", json={"origin": "import", "setup": setup}).json()
    assert case["inputs"]["requirements"]["bus_voltage_v"] == 300.0
    assert case["inputs"]["requirements"]["phase_current_a"] == 25.0


def test_materials_section_wins_over_machine_materials(client):
    _, r = _setup(client)
    setup = r.json()
    setup["geometry"]["machine"]["materials"] = {"stator": "M19", "rotor": "M19"}
    case = client.post("/api/cases", json={"origin": "import", "setup": setup}).json()
    assert case["inputs"]["design"]["machine"]["materials"]["stator"] == "10JNEX900"


def test_schema_and_unknown_keys_are_422(client):
    _, r = _setup(client)
    good = r.json()
    bad = client.post("/api/setup/check", json=good | {"schema": "other"})
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"] == ["body", "schema"]
    geometry = good["geometry"] | {"colour": 1}
    bad = client.post("/api/setup/check", json=good | {"geometry": geometry})
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"] == ["body", "geometry", "colour"]
    fixed = good["winding"] | {"mode": "fixed"}
    assert client.post("/api/setup/check", json=good | {"winding": fixed}).status_code == 422


def test_check_with_only_a_search_section(client):
    r = client.post("/api/setup/check", json={"schema": "srm-setup", "version": 1, "search": {"seed": 3}})
    assert r.status_code == 200, r.text
    assert r.json()["search"]["seed"] == 3 and r.json()["geometry"] is None


def test_import_missing_sections(client):
    _, r = _setup(client)
    setup = {k: v for k, v in r.json().items() if k not in ("winding", "materials")}
    r = client.post("/api/cases", json={"origin": "import", "setup": setup})
    assert r.status_code == 422
    assert r.json()["errors"] == [{"loc": [], "msg": "missing sections: materials, winding"}]
    assert client.get("/api/cases").json()[0]["label"] == "8/6 reference"   # nothing was created


def test_import_reports_errors_at_setup_paths(client):
    wired = REQ | {"wires": [WIRE], "phase_current_a": 30.0}
    case = _reference(client, wired)
    setup = client.get(f"/api/cases/{case['id']}/setup").json()
    setup["winding"] = {"mode": "fixed", "fixed": {"turns": 10, "wire": 3}}
    r = client.post("/api/cases", json={"origin": "import", "setup": setup})
    assert r.status_code == 422
    assert ["winding", "fixed", "wire"] in [e["loc"] for e in r.json()["errors"]]
    setup["materials"] = {"stator": "nope"}
    r = client.post("/api/cases", json={"origin": "import", "setup": setup})
    assert ["materials", "stator"] in [e["loc"] for e in r.json()["errors"]]
    setup["geometry"]["machine"]["air_gap"] = 0.5
    r = client.post("/api/cases", json={"origin": "import", "setup": setup})
    assert any(e["loc"][:2] == ["geometry", "machine"] for e in r.json()["errors"])


def test_export_of_an_invalid_draft_is_422(client):
    case = _reference(client)
    client.patch(f"/api/cases/{case['id']}", json={"inputs": {"design": {"machine": {}}}})
    r = client.get(f"/api/cases/{case['id']}/setup")
    assert r.status_code == 422 and r.json()["errors"]
    assert client.get("/api/cases/nope/setup").status_code == 404


def test_file_name_is_sanitised(client):
    case = _reference(client)
    client.patch(f"/api/cases/{case['id']}", json={"label": 'a"b/c\\d\x01\u00e9'})
    r = client.get(f"/api/cases/{case['id']}/setup")
    assert r.headers["content-disposition"] == 'attachment; filename="ab-cd.srm-setup.json"'


def test_export_refuses_mesh_settings_a_setup_file_cannot_hold(client):
    case = _reference(client)
    url = f"/api/cases/{case['id']}"
    for mesh in ({"preset": "reference"}, {"preset": "full", "outer_air_thickness": 0.01}):
        design = case["inputs"]["design"] | {"mesh": mesh}
        assert client.patch(url, json={"inputs": case["inputs"] | {"design": design}}).status_code == 200
        r = client.get(f"{url}/setup")
        assert r.status_code == 422, r.text
        assert r.json()["errors"][0]["loc"][:1] == ["design"]   # check_case rejects "reference"; a custom mesh is ours
