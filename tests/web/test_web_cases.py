import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from srmcore.maps.checks import Check
from srmcore.maps.validation import BudgetRow, EmValidation, UncertaintyBudget
from srmweb.serialize import to_json
from web_support import REQ, evaluation, make_client, store_search

NAN = float("nan")


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c


def _candidate(client):
    job_id = store_search(client, evaluation("c0"), evaluation("bad", ok=False))
    return client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c0"})


def _reference(client, name="8/6", **over):
    return client.post("/api/cases", json={"origin": "reference", "name": name, "requirements": REQ, **over})


def test_open_candidate_as_case(client):
    r = _candidate(client)
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["stale"] is False and case["origin"] == "candidate" and not case["show_in_graphs"]
    assert case["label"] == "8/6 c0" and case["poles"] == "8/6" and case["preset"] == "screening"
    assert case["inputs"]["winding"] == "auto"
    assert case["inputs"]["margin"] == 1.1 and case["inputs"]["j_peak"] == 1.2e7
    assert case["inputs"]["j_limit"] is None
    assert case["evaluation"]["torque_ratio"] == 1.1 and case["torque_ratio"] == 1.1
    assert case["evaluation"]["curves"]["la_lu"] == [None, 1.0]
    assert case["status"] == "ok" and case["feasible"] is True and case["validated"] is False
    assert case["validation"] is None and case["jobs"] == []


def test_failed_or_missing_candidate(client):
    job_id = store_search(client, evaluation("bad", ok=False))

    def post(**kw):
        return client.post("/api/cases", json={"origin": "candidate", **kw})

    assert post(job_id=job_id, candidate_id="bad").status_code == 409
    assert post(job_id=job_id, candidate_id="nope").status_code == 404
    assert post(job_id="nope", candidate_id="c0").status_code == 404
    assert client.get("/api/cases").json() == []


def test_reference_case_is_a_stale_draft(client):
    r = _reference(client, "12/8", preset="screening")
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["stale"] is True and case["evaluation"] is None and case["status"] is None
    assert case["label"] == "12/8 reference" and case["poles"] == "12/8" and case["preset"] == "screening"
    assert case["inputs"]["design"]["machine"]["materials"]["stator"] == "10JNEX900"
    assert _reference(client).json()["preset"] == "full"
    assert _reference(client, "5/5").status_code == 422


def test_references(client):
    refs = client.get("/api/references").json()
    assert [r["name"] for r in refs] == ["8/6", "12/8", "24/16"]
    assert refs[1]["machine"]["n_stator_poles"] == 12


def test_edit_copies_inputs_into_a_draft(client):
    parent = _candidate(client).json()
    body = {"origin": "edit", "parent_case_id": parent["id"], "inputs": parent["inputs"]}
    r = client.post("/api/cases", json=body)
    assert r.status_code == 201, r.text
    edit = r.json()
    assert edit["stale"] and edit["origin"] == "edit" and edit["parent_case_id"] == parent["id"]
    assert edit["label"] == "8/6 c0 · edit" and edit["evaluation"] is None
    assert client.post("/api/cases", json=body | {"parent_case_id": "nope"}).status_code == 404


def test_patch_inputs_of_evaluated_case_409(client):
    case = _candidate(client).json()
    r = client.patch(f"/api/cases/{case['id']}", json={"inputs": case["inputs"]})
    assert r.status_code == 409
    assert r.json()["detail"] == "evaluated cases are read-only; edit creates a new case"
    assert client.patch(f"/api/cases/{case['id']}", json={"label": "keep"}).json()["label"] == "keep"


def test_draft_holds_raw_invalid_inputs(client):
    case = _reference(client).json()
    r = client.patch(f"/api/cases/{case['id']}", json={"inputs": {"design": {"machine": {}}}})
    assert r.status_code == 200, r.text
    assert r.json()["inputs"] == {"design": {"machine": {}}} and r.json()["poles"] is None
    assert client.get(f"/api/cases/{case['id']}").json()["preset"] is None
    assert [c["poles"] for c in client.get("/api/cases").json()] == [None]
    for bad in ("text", ["list"]):
        assert client.patch(f"/api/cases/{case['id']}", json={"inputs": bad}).status_code == 422


def test_patch_metadata(client):
    case = _reference(client).json()
    url = f"/api/cases/{case['id']}"
    r = client.patch(url, json={"flag": "best", "comment": "c" * 2000, "label": "mine"})
    assert (r.json()["flag"], r.json()["label"], len(r.json()["comment"])) == ("best", "mine", 2000)
    assert client.patch(url, json={"flag": ""}).json()["flag"] == ""
    assert client.patch(url, json={"flag": "f" * 41}).status_code == 422
    assert client.patch(url, json={"comment": "c" * 2001}).status_code == 422
    assert client.patch(url, json={"nope": 1}).status_code == 422
    assert client.patch("/api/cases/nope", json={}).status_code == 404


def test_seventh_show_in_graphs_409(client):
    ids = [_reference(client).json()["id"] for _ in range(7)]

    def show(case_id, on=True):
        return client.patch(f"/api/cases/{case_id}", json={"show_in_graphs": on})

    assert all(show(i).status_code == 200 for i in ids[:6])
    assert show(ids[0]).status_code == 200      # already shown
    assert show(ids[6]).status_code == 409
    assert show(ids[0], False).json()["show_in_graphs"] is False
    assert show(ids[6]).status_code == 200


def test_delete_case_while_job_active_409(client):
    store = client.app.state.store
    case = _reference(client).json()
    job_id = store.create_job("evaluate", {"case_id": case["id"]})
    r = client.get(f"/api/cases/{case['id']}")
    assert [j["id"] for j in r.json()["jobs"]] == [job_id] and r.json()["jobs"][0]["active"]
    assert client.delete(f"/api/cases/{case['id']}").status_code == 409
    store.set_status(job_id, "cancelled")
    assert client.delete(f"/api/cases/{case['id']}").status_code == 204
    assert client.get(f"/api/cases/{case['id']}").status_code == 404
    assert client.delete(f"/api/cases/{case['id']}").status_code == 404


def test_validation_result_and_label(client):
    case = _candidate(client).json()
    budget = UncertaintyBudget({"la": 1.0}, {"la": 1.1}, (BudgetRow("mesh", {"la": 0.01}, "n"),), {"la": 0.01})
    ok = EmValidation("EM-validated", (Check("preset", "pass", 1.0, NAN, "full"),), budget, "0.4.0", {"stator": "B"})
    client.app.state.store.put_result(None, to_json(ok), kind="validate", case_id=case["id"])
    got = client.get(f"/api/cases/{case['id']}").json()
    assert got["validated"] is True and got["validation"]["label"] == "EM-validated"
    assert got["validation"]["checks"][0]["limit"] is None
    assert got["validation"]["budget"]["rows"][0]["rel"] == {"la": 0.01}
    assert got["validation"]["engine_version"] == "0.4.0" and got["validation"]["material_grades"] == {"stator": "B"}
    assert [c["validated"] for c in client.get("/api/cases").json()] == [True]


def test_list_cases_summaries_newest_first(client):
    a = _candidate(client).json()
    b = _reference(client).json()
    rows = client.get("/api/cases").json()
    assert [r["id"] for r in rows] == [b["id"], a["id"]]
    assert "inputs" not in rows[0] and rows[1]["power_ratio"] == 1.2 and rows[1]["mass_kg"] == 1.0
    assert rows[0]["torque_ratio"] is None and rows[0]["feasible"] is None


def test_evaluation_stored_without_new_envelope_fields_still_serves(client):
    from srmweb.results import EvaluationOut
    from web_support import SEARCH_REQUEST, search_body

    body = search_body(evaluation("c0"))
    env = body["evaluations"][0]["envelope"]
    for k in ("line_mean", "line_rms", "power_factor", "waveforms"):
        env.pop(k, None)
    EvaluationOut.model_validate(body["evaluations"][0])
    job_id = client.app.state.store.create_job("search", SEARCH_REQUEST)
    client.app.state.store.put_result(job_id, body, kind="search")
    client.app.state.store.set_status(job_id, "done")
    case = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c0"}).json()
    r = client.get(f"/api/cases/{case['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["evaluation"]["envelope"]["power_factor"] is None
