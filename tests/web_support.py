"""Fake search results and a test client for the srmweb case and result tests."""
import numpy as np
from fastapi.testclient import TestClient

from conftest import make_8_6
from srmapp.curves import MapCurves
from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, MapArrays
from srmapp.pipeline import SearchResult
from srmapp.requirements import Requirements
from srmapp.sizing.winding import Winding
from srmcore.maps.results import KeyNumbers
from srmcore.model.design import Design, MeshSettings
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner
from srmweb.serialize import search_result_json

NAN = float("nan")
REQ = dict(peak_power_w=10000.0, peak_torque_nm=31.83, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
SEARCH_REQUEST = {"requirements": REQ, "settings": {"margin": 1.1, "j_peak": 1.2e7}}


def make_client(tmp_path):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1, None, 10, tmp_path / "nostatic")
    return TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(store, st, run_fn=lambda k, r, p, ctx: {})))


def evaluation(ident: str, ok: bool = True) -> Evaluation:
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    if not ok:
        return Evaluation(ident, design, "MapFailed", "boom", 1.0, None, NAN, NAN, NAN, NAN, NAN, False, None, None)
    a = np.array([0.1, 0.2])
    env = Envelope(a, a, a, a, a, np.array([0.0, NAN]), a, a, a, None, a, a, a)
    m = MapArrays(a, a, np.zeros((2, 2)), np.full((2, 2), NAN))
    key = KeyNumbers(0.01, 0.002, 5.0, 30.0, 0.5, 20.0, 0.0, 0.5)
    curves = MapCurves(a, np.ones((2, 2)), a, a, 0.01, a, a, a, np.array([NAN, 1.0]))
    return Evaluation(ident, design, "ok", "", 1.0, Winding(10, 1, 1e-6, 5.0, 0.1, 0.2, None), 1.1, 1.2, 1000.0,
                      2.0, 0.9, True, env, key, i_rms_a=3.0, j_rms=NAN, map=m, curves=curves)


def search_body(*evaluations: Evaluation) -> dict:
    req = Requirements(**REQ)
    return search_result_json(SearchResult(req, len(evaluations), {"x": 1}, 0, tuple(evaluations), False))


def store_search(client, *evaluations: Evaluation) -> str:
    store = client.app.state.store
    job_id = store.create_job("search", SEARCH_REQUEST)
    store.put_result(job_id, search_body(*evaluations), kind="search")
    store.set_status(job_id, "done")
    return job_id
