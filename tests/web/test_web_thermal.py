import dataclasses
import json

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from srmapp.cooling import CoolingSetup, EndSpray
from srmapp.thermal import BudgetShare, Rating, RequirementCheck, SpeedRating
from srmapp.thermal_fields import KINDS, ThermalFields, read_fields
from srmcore.post.rotor_stress import GapClosure, RotorStress
from srmcore.thermal.solve import HotSpot
from srmweb import results, thermal_files
from srmweb.serialize import evaluation_json, rating_json
from srmapp.requirements import Requirements
from web_support import REQ, evaluation, make_client, store_search, unpack


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c


def _rating():
    def sr(rpm, k):
        return SpeedRating(rpm, 5.0, 3.0 * k, 4.0 * k, HotSpot(140.0, "coil_A1+"), HotSpot(150.0, "end_winding"),
                           90.0, 95.0, 80.0, 85.0, 7, 60, "a speed note", 2.0)

    stress = RotorStress("ok", "", 7200.0, 1e8, 2e8, 1.5, "pole_root", "von_mises", 5e8, 2.4, 9000.0)
    gap = {"cold": GapClosure(1e-6, None, None, None, "no data"), "hot": GapClosure(1e-6, 2e-6, 1e-6, 2e-6, "")}
    return Rating((sr(3000.0, 1.0), sr(6000.0, 1.0)), (sr(3000.0, 0.8), sr(6000.0, 0.8)),
                  (BudgetShare("iron", 3000.0, 4.0),), 155.0, "F", CoolingSetup(end_spray=EndSpray(inlet_c=60.0, flow_m3s=1e-5)),
                  stress, gap, 1.1, 12, ("a note",), "0.9.0")


def _fields(n=4):
    return ThermalFields(np.zeros((n, 2), np.float32), np.array([[0, 1, 2], [1, 2, 3]], np.int32),
                         np.array([0, 3], np.uint8), np.array([3000.0, 6000.0]),
                         np.full((2, n), 100.0, np.float32), np.full((2, n), np.nan, np.float32),
                         np.array([110.0, np.nan]), np.array([np.nan, np.nan]))


def test_rating_json_round_trips_through_rating_out():
    r = _rating()
    out = results.RatingOut.model_validate(rating_json(r, air_gap_m=3e-4))
    json.dumps(out.model_dump(), allow_nan=False)
    assert out.shares[0].row == "iron" and out.shares[0].hot_spot_rise_k == 4.0
    assert out.gap.air_gap_m == 3e-4 and out.gap.cases["hot"].closure == 2e-6 and out.gap.cases["cold"].closure is None
    assert out.stress.governing == "pole_root" and out.stress.speed_limit_rpm == 9000.0
    assert out.cooling.kind == "jacket + end spray" and out.cooling.placeholder
    assert out.torque_factor == 1.1 and out.srmapp_version == "0.9.0"
    s = out.speeds[0]
    assert s.rated.envelope_nm == 5.0 and s.rated.start_nm == 2.0 and s.nominal.note == "a speed note"
    assert s.rated_continuous_nm == pytest.approx(2.4)


def test_pre_r5d_rating_still_loads():
    old = {"speeds": [{"rpm": 3000.0, "nominal_continuous_nm": 3.0, "nominal_peak_nm": 4.0,
                       "rated_continuous_nm": 2.4, "rated_peak_nm": 3.2, "hot_spot_c": 140.0, "hot_spot_at": "x",
                       "peak_hot_spot_c": 150.0, "peak_hot_spot_at": "y"}],
           "limit_c": 155.0, "insulation_class": "F", "stress_status": "ok", "stress_safety_factor": 2.4,
           "notes": []}
    out = results.RatingOut.model_validate(old)
    assert out.shares == [] and out.gap is None and out.cooling is None


def test_evaluation_json_carries_thermal_keys():
    ev = dataclasses.replace(evaluation("c0"), rating=_rating(), thermal_check=RequirementCheck(True, None, (1.0,), (2.0,), ()))
    body = evaluation_json(ev, fields_key="j_c0", requirements=Requirements(**REQ))
    out = results.EvaluationOut.model_validate(body)
    assert out.thermal_fields == "j_c0" and out.thermal_check.holds and out.thermal_summary is not None
    assert isinstance(out.thermal_summary.shares, list)
    assert evaluation_json(evaluation("c0"))["thermal_fields"] is None
    old = evaluation_json(evaluation("c0"))
    for k in ("thermal_check", "thermal_summary", "thermal_fields"):
        old.pop(k)
    assert results.EvaluationOut.model_validate(old).thermal_fields is None


def _case_with_fields(client, tmp_path, write=True):
    job_id = store_search(client, evaluation("c1"))
    case_id = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id,
                                              "candidate_id": "c1"}).json()["id"]
    key = thermal_files.fields_key("jobX", "c1")
    if write:
        thermal_files.write(tmp_path / "cache", key, _fields())
    store = client.app.state.store
    body = store.get_result(job_id)["evaluations"][0]
    body["thermal_fields"] = key
    with store._db() as con:
        con.execute("UPDATE results SET body = ? WHERE case_id = ? AND kind = 'evaluate'", (json.dumps(body), case_id))
    return case_id


def test_fields_route_serves_pack(client, tmp_path):
    case_id = _case_with_fields(client, tmp_path)
    r = client.get(f"/api/cases/{case_id}/thermal/fields")
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    header, _, arrays = unpack(r.content)
    assert header["meta"]["rpm"] == [3000.0, 6000.0] and header["meta"]["kinds"] == list(KINDS)
    assert header["meta"]["end_winding_steady_c"] == [110.0, None]
    assert arrays["steady"].shape == (2, 4) and arrays["triangles"].dtype == np.uint32


def test_fields_route_410_after_clear(client, tmp_path):
    case_id = _case_with_fields(client, tmp_path)
    assert client.delete("/api/settings/cache").status_code == 204
    assert client.get(f"/api/cases/{case_id}/thermal/fields").status_code == 410


def test_fields_route_404_unrated(client):
    job_id = store_search(client, evaluation("c1"))
    case_id = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id,
                                              "candidate_id": "c1"}).json()["id"]
    assert client.get(f"/api/cases/{case_id}/thermal/fields").status_code == 404
    assert client.get("/api/cases/nope/thermal/fields").status_code == 404


def test_cache_counts_thermal(client, tmp_path):
    before = client.get("/api/settings/cache").json()["files"]
    thermal_files.write(tmp_path / "cache", "k", _fields())
    assert client.get("/api/settings/cache").json()["files"] == before + 1
    client.delete("/api/settings/cache")
    assert client.get("/api/settings/cache").json()["files"] == 0


def test_same_design_two_searches_two_files(tmp_path):
    a, b = thermal_files.fields_key("jobA", "abc123"), thermal_files.fields_key("jobB", "abc123")
    assert a != b
    thermal_files.write(tmp_path, a, _fields())
    thermal_files.write(tmp_path, b, _fields(5))
    assert read_fields(thermal_files.path(tmp_path, a)).steady.shape == (2, 4)
    assert read_fields(thermal_files.path(tmp_path, b)).steady.shape == (2, 5)
