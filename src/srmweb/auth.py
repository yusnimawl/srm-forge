"""Token login and in-memory session cookies."""
from __future__ import annotations

import hmac
import secrets
import threading

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

COOKIE = "srmweb_session"


class Sessions:
    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._lock = threading.Lock()

    def create(self) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._ids.add(sid)
        return sid

    def valid(self, sid: str | None) -> bool:
        with self._lock:
            return sid is not None and sid in self._ids

    def remove(self, sid: str | None) -> None:
        with self._lock:
            self._ids.discard(sid)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


def require_auth(request: Request) -> None:
    if request.app.state.settings.token is None:
        return
    if not request.app.state.sessions.valid(request.cookies.get(COOKIE)):
        raise HTTPException(401, "login required")


auth_router = APIRouter(prefix="/api")


@auth_router.post("/login", status_code=204)
def login(body: LoginIn, request: Request) -> Response:
    token = request.app.state.settings.token
    response = Response(status_code=204)
    if token is None:
        return response
    if not hmac.compare_digest(body.token.encode(), token.encode()):
        raise HTTPException(401, "wrong token")
    response.set_cookie(COOKIE, request.app.state.sessions.create(),
                        httponly=True, samesite="strict", path="/")
    return response


@auth_router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.app.state.sessions.remove(request.cookies.get(COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return response


@auth_router.get("/session")
def session(request: Request) -> dict:
    required = request.app.state.settings.token is not None
    logged_in = (not required
                 or request.app.state.sessions.valid(request.cookies.get(COOKIE)))
    return {"auth_required": required, "logged_in": logged_in}
