import pytest
from fastapi.testclient import TestClient

from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner


def _client(tmp_path, token):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1,
                 token, 10, tmp_path)
    app = create_app(s, runner_factory=lambda store, st: JobRunner(
        store, st, run_fn=lambda kind, req, rep: {"ok": 1}))
    return TestClient(app)


@pytest.fixture
def open_client(tmp_path):
    with _client(tmp_path, None) as c:
        yield c


@pytest.fixture
def locked(tmp_path):
    with _client(tmp_path, "t0k") as c:
        yield c


def test_auth_off_everything_open(open_client):
    assert open_client.get("/api/jobs").status_code == 200
    r = open_client.post("/api/login", json={"token": "anything"})
    assert r.status_code == 204
    assert "set-cookie" not in r.headers
    assert open_client.get("/api/session").json() == {
        "auth_required": False, "logged_in": True}


def test_protected_routes_need_login(locked):
    for path in ("/api/jobs", "/api/health", "/api/jobs/x", "/api/jobs/x/events"):
        assert locked.get(path).status_code == 401
    assert locked.post("/api/jobs", json={}).status_code == 401
    assert locked.delete("/api/jobs/x").status_code == 401


def test_wrong_token_rejected(locked):
    assert locked.post("/api/login", json={"token": "nope"}).status_code == 401
    assert locked.get("/api/jobs").status_code == 401


def test_login_sets_strict_httponly_cookie(locked):
    r = locked.post("/api/login", json={"token": "t0k"})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("srmweb_session=")
    assert "HttpOnly" in cookie and "samesite=strict" in cookie.lower()
    assert "Path=/" in cookie and "Secure" not in cookie
    assert locked.get("/api/jobs").status_code == 200
    assert locked.get("/api/health").status_code == 200


def test_logout_ends_session(locked):
    locked.post("/api/login", json={"token": "t0k"})
    assert locked.post("/api/logout").status_code == 204
    assert locked.get("/api/jobs").status_code == 401


def test_session_endpoint_reflects_state(locked):
    assert locked.get("/api/session").json() == {
        "auth_required": True, "logged_in": False}
    locked.post("/api/login", json={"token": "t0k"})
    assert locked.get("/api/session").json() == {
        "auth_required": True, "logged_in": True}
    locked.post("/api/logout")
    assert locked.get("/api/session").json()["logged_in"] is False


def test_forged_cookie_rejected(locked):
    locked.cookies.set("srmweb_session", "forged")
    assert locked.get("/api/jobs").status_code == 401


def test_sessions_not_shared_between_apps(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    with _client(tmp_path / "1", "t0k") as a, _client(tmp_path / "2", "t0k") as b:
        a.post("/api/login", json={"token": "t0k"})
        b.cookies.set("srmweb_session", a.cookies["srmweb_session"])
        assert b.get("/api/jobs").status_code == 401
