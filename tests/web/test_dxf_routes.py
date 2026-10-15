import math

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient

from conftest import make_8_6
from srmapp.case import CaseInputs, reference_design
from srmapp.requirements import Requirements
from srmapp.sizing.estimates import active_mass
from srmcore.model.design import Design, MeshSettings
from srmcore.model.iron import IronArc, IronLine
from srmcore.topology.dxf_io import import_dxf, write_dxf
from srmcore.topology.imported import parametric_iron
from srmweb.cases import check_case
from srmweb.geometry import outline_svg
from web_support import evaluation, make_client, store_search

MM = 1e-3
SMALL = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)


def _grooved_outer(radius, n, depth=1 * MM, half_width=1 * MM):
    d = math.asin(half_width / radius)

    def at(r, a):
        return (r * math.cos(a), r * math.sin(a))

    segs = []
    for k in range(n):
        a, a_next = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        left, apex, right = at(radius, a - d), at(radius - depth, a), at(radius, a + d)
        segs += [IronLine(start=left, end=apex), IronLine(start=apex, end=right),
                 IronArc(start=right, end=at(radius, a_next - d), center=(0.0, 0.0))]
    return tuple(segs)


def _circle(cx, cy, r):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(cx, cy)) for i in range(4))


def _iron_machine(n=8, holes=0, hole_r=1 * MM):
    p = make_8_6()
    kw = {"stator_outer": _grooved_outer(p.stator_outer_radius, n)}
    if holes:
        r = p.stator_outer_radius - 4 * MM
        kw["stator_holes"] = tuple(_circle(r * math.cos(k), r * math.sin(k), hole_r) for k in (2 * math.pi * j / 8 for j in range(holes)))
    return p.model_copy(update={"iron": parametric_iron(p).model_copy(update=kw)})


def _inputs(machine=None) -> dict:
    design = Design(machine=machine or make_8_6(), mesh=MeshSettings(preset="screening"))
    return CaseInputs(requirements=Requirements(**SMALL), design=design).model_dump(mode="json")


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c


def _case(client, machine=None, label="parent"):
    return client.app.state.store.create_case(origin="import", inputs=_inputs(machine), label=label, stale=True)


def _upload(client, case_id, data: bytes):
    return client.post(f"/api/cases/{case_id}/dxf", files={"file": ("m.dxf", data, "application/dxf")})


def test_export_reads_back_cleanly(client):
    cid = _case(client, label="my case")
    r = client.get(f"/api/cases/{cid}/dxf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/dxf")
    assert 'filename="my case.dxf"' in r.headers["content-disposition"]
    iron, issues = import_dxf(r.content, make_8_6())
    assert iron is not None and issues == []


def test_import_creates_linked_stale_case(client):
    cid = _case(client, label="base")
    r = _upload(client, cid, write_dxf(_iron_machine(8)))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["warnings"] == [] or all({"loc", "msg"} <= set(w) for w in out["warnings"])
    case = out["case"]
    assert case["origin"] == "dxf" and case["parent_case_id"] == cid and case["stale"]
    assert case["label"] == "DXF edit of base"
    assert case["inputs"]["design"]["machine"]["iron"] is not None
    assert case["evaluation"] is None


def test_import_two_grooves_refused(client):
    cid = _case(client)
    r = _upload(client, cid, write_dxf(_iron_machine(2)))
    assert r.status_code == 422
    errors = r.json()["errors"]
    assert errors and all(e["loc"] == ["iron"] for e in errors)
    assert any("repeat" in e["msg"] for e in errors)
    assert len(client.get("/api/cases").json()) == 1


def test_import_too_large(client):
    cid = _case(client)
    assert _upload(client, cid, b"0" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_import_unknown_case(client):
    assert _upload(client, "nope", b"x").status_code == 404


def test_check_case_runs_iron_checks():
    machine = _iron_machine(2)
    inputs, errors, _ = check_case(_inputs(machine))
    assert inputs is None
    assert errors and all(e["loc"] == ["design", "machine", "iron"] for e in errors)
    assert check_case(_inputs(_iron_machine(8)))[0] is not None


def test_patch_params_on_dxf_case_rechecks(client):
    cid = _case(client)
    case = _upload(client, cid, write_dxf(_iron_machine(8))).json()["case"]
    inputs = case["inputs"]
    inputs["design"]["machine"]["air_gap"] *= 3
    assert client.patch(f"/api/cases/{case['id']}", json={"inputs": inputs}).status_code == 200
    r = client.post("/api/validate", json={"inputs": inputs})
    assert any(e["loc"] == ["design", "machine", "iron"] for e in r.json()["errors"])


def test_compare_without_parent_404(client):
    assert client.get(f"/api/cases/{_case(client)}/compare").status_code == 404


def test_compare_unevaluated_parent(client):
    cid = _case(client)
    child = _upload(client, cid, write_dxf(_iron_machine(8))).json()["case"]
    out = client.get(f"/api/cases/{child['id']}/compare").json()
    assert out["parent_id"] == cid and out["parent_evaluated"] is False
    assert [r["name"] for r in out["rows"]] == ["La", "Lu", "Peak torque", "Flux linkage max",
                                                "Stator iron", "Rotor iron", "Total mass"]
    assert all(r["before"] is None for r in out["rows"])
    assert all(r["after"] is None for r in out["rows"])


def test_compare_evaluated(client):
    job_id = store_search(client, evaluation("c0"))
    parent = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c0"}).json()
    child = _upload(client, parent["id"], write_dxf(_iron_machine(8))).json()["case"]
    out = client.get(f"/api/cases/{child['id']}/compare").json()
    assert out["parent_evaluated"] is True
    rows = {r["name"]: r for r in out["rows"]}
    assert rows["La"]["unit"] == "mH" and rows["La"]["before"] == pytest.approx(10.0)
    assert rows["Peak torque"]["before"] == pytest.approx(30.0)
    assert rows["La"]["after"] is None
    machine = CaseInputs.model_validate(parent["inputs"]).design.machine
    stator = active_mass(reference_design(CaseInputs.model_validate(parent["inputs"])).machine).stator_iron
    assert rows["Stator iron"]["before"] == pytest.approx(stator)
    assert rows["Total mass"]["before"] == pytest.approx(1.0)
    assert machine.iron is None


def test_geometry_svg_has_one_path_per_hole():
    plain = outline_svg(_iron_machine(8))
    holed = outline_svg(_iron_machine(8, holes=8))
    assert holed["stator"].count("M") == plain["stator"].count("M") + 8


def _dxf_case(client, **kw):
    parent = _case(client)
    return _upload(client, parent, write_dxf(_iron_machine(8, **kw))).json()["case"]


def test_validate_with_iron_and_bad_params_reports_params_not_500(client):
    machine = _iron_machine(8).model_copy(update={"stator_pole_arc": 1.2})
    inputs, errors, _ = check_case(_inputs(machine))
    assert inputs is None and errors and all(e["loc"][2] != "iron" for e in errors)
    r = client.post("/api/validate", json={"inputs": _inputs(machine)})
    assert r.status_code == 200 and r.json()["errors"]


def test_dxf_routes_on_invalid_draft_give_422(client):
    bad = _iron_machine(8).model_copy(update={"stator_pole_arc": 1.2})
    cid = _case(client, bad)
    assert client.get(f"/api/cases/{cid}/dxf").status_code == 422
    assert _upload(client, cid, write_dxf(_iron_machine(8))).status_code == 422


def test_reimport_compares_with_parent_iron(client, monkeypatch):
    from srmweb import api
    case = _dxf_case(client, holes=8, hole_r=1.5 * MM)
    seen = []
    real = api.import_dxf
    monkeypatch.setattr(api, "import_dxf", lambda data, p: seen.append(p) or real(data, p))
    r = _upload(client, case["id"], client.get(f"/api/cases/{case['id']}/dxf").content)
    assert r.status_code == 201, r.text
    assert seen[0].iron.model_dump(mode="json") == case["inputs"]["design"]["machine"]["iron"]


def test_garbage_upload_refused_without_case(client):
    cid = _case(client)
    r = _upload(client, cid, bytes(range(256)) * 20)
    assert r.status_code == 422
    assert r.json()["errors"] and all(e["loc"] == ["iron"] for e in r.json()["errors"])
    assert len(client.get("/api/cases").json()) == 1


def test_export_of_dxf_case_keeps_holes(client):
    case = _dxf_case(client, holes=8)
    iron = case["inputs"]["design"]["machine"]["iron"]
    assert len(iron["stator_holes"]) == 8
    data = client.get(f"/api/cases/{case['id']}/dxf").content
    back, issues = import_dxf(data, CaseInputs.model_validate(case["inputs"]).design.machine)
    assert back is not None and back.model_dump(mode="json") == iron
