import math
import sys

import pytest
from conftest import make_8_6
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner


def _client(tmp_path, token=None, static=None, run_fn=lambda kind, req, rep: {"ok": 1}):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1,
                 token, 10, static or tmp_path / "nostatic")
    app = create_app(s, runner_factory=lambda store, st: JobRunner(store, st, run_fn=run_fn))
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    with _client(tmp_path) as c:
        yield c


def test_geometry_route(client):
    r = client.post("/api/geometry", json=make_8_6().model_dump(mode="json"))
    assert r.status_code == 200
    assert len(r.json()["coils"]) == 16


def test_geometry_route_fit_failure(client):
    body = make_8_6(stator_pole_arc=math.radians(40)).model_dump(mode="json")
    r = client.post("/api/geometry", json=body)
    assert r.status_code == 422
    err = r.json()["detail"][0]
    assert err["loc"][0] == "body" and err["msg"] and err["type"]


def test_materials(client):
    mats = {m["name"]: m for m in client.get("/api/materials").json()}
    assert mats["10JNEX900"]["grade"] == "B"
    assert mats["10JNEX900"]["thickness_mm"] == pytest.approx(0.1)
    assert mats["10JNEX900"]["js"] == pytest.approx(1.8)
    assert "copper" not in mats


def test_cache_settings(tmp_path, client):
    cache = tmp_path / "cache"
    assert client.get("/api/settings/cache").json() == {
        "path": str(cache), "files": 0, "bytes": 0}
    cache.mkdir()
    (cache / "x.h5").write_bytes(b"12345")
    (cache / "keep.txt").write_bytes(b"1")
    assert client.get("/api/settings/cache").json()["files"] == 1
    assert client.get("/api/settings/cache").json()["bytes"] == 5
    assert client.delete("/api/settings/cache").status_code == 204
    assert not (cache / "x.h5").exists() and (cache / "keep.txt").exists()


def test_cache_delete_conflicts_while_running(tmp_path):
    import threading
    gate = threading.Event()
    with _client(tmp_path, run_fn=lambda k, r, rep: gate.wait(10) and {"ok": 1}) as c:
        try:
            jid = c.post("/api/jobs", json={"kind": "search", "payload": {"requirements": dict(
                peak_power_w=10000.0, peak_torque_nm=31.83, base_speed_rpm=3000.0,
                max_speed_rpm=6000.0)}}).json()["id"]
            for _ in range(100):
                if c.get(f"/api/jobs/{jid}").json()["status"] == "running":
                    break
                import time
                time.sleep(0.05)
            assert c.delete("/api/settings/cache").status_code == 409
        finally:
            gate.set()


def test_docs_behind_auth(tmp_path):
    with _client(tmp_path, token="t0k") as c:
        assert c.get("/api/docs").status_code == 401
        assert c.get("/api/openapi.json").status_code == 401
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
        c.post("/api/login", json={"token": "t0k"})
        assert c.get("/api/docs").status_code == 200
        assert "/api/jobs" in c.get("/api/openapi.json").json()["paths"]


def test_spa_fallback(tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("1")
    (tmp_path / "secret.txt").write_text("nope")
    with _client(tmp_path, static=static) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/runs/abc").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "1"
        assert c.get("/..%2fsecret.txt").text == "<html>app</html>"
        r = c.get("/api/nothing")
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_no_frontend_message(client):
    r = client.get("/")
    assert r.status_code == 200 and "Frontend not built" in r.text


def test_openapi_dump(tmp_path):
    import json
    import subprocess
    out = tmp_path / "o.json"
    subprocess.run([sys.executable, "-m", "srmweb.openapi", str(out)], check=True)
    assert "/api/jobs" in json.loads(out.read_text())["paths"]
