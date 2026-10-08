"""FastAPI app factory and job routes."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

import srmcore
import srmweb
from srmweb.auth import Sessions, auth_router, require_auth
from srmweb.config import Settings
from srmweb.jobs import JobRunner, QueueFull
from srmweb.schemas import JobIn, JobOut
from srmweb.store import Store

_RESUMABLE = ("interrupted", "cancelled", "failed")
_POLL_S = 0.5
_KEEPALIVE_S = 15.0
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(event: str, out: JobOut) -> str:
    return f"event: {event}\ndata: {out.model_dump_json()}\n\n"


def _job_out(job: dict, runner: JobRunner, live=...) -> JobOut:
    if live is ...:
        live = runner.progress(job["id"])
    if live is not None:
        job = {**job, "progress": live[1]}
    return JobOut(**{k: job[k] for k in JobOut.model_fields})


def _submit(runner: JobRunner, kind: str, request: dict) -> dict:
    try:
        return {"id": runner.submit(kind, request)}
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc


def create_app(settings: Settings,
               runner_factory: Callable[[Store, Settings], JobRunner] = JobRunner) -> FastAPI:
    store = Store(settings.db)
    runner = runner_factory(store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runner.start()
        yield
        runner.stop()

    app = FastAPI(title="srmweb", lifespan=lifespan)
    app.state.settings, app.state.store, app.state.runner = settings, store, runner
    app.state.sessions = Sessions()
    router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

    def job_or_404(job_id: str) -> dict:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id}")
        return job

    @router.get("/health")
    def health():
        return {"version": srmweb.__version__, "srmcore": srmcore.__version__}

    @router.post("/jobs", status_code=201)
    def create_job(job: JobIn):
        return _submit(runner, job.kind, job.payload.model_dump(mode="json"))

    @router.get("/jobs", response_model=list[JobOut])
    def list_jobs():
        return [_job_out(j, runner) for j in store.list_jobs()]

    @router.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str):
        return _job_out(job_or_404(job_id), runner)

    @router.get("/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request):
        job_or_404(job_id)

        async def stream():
            seen, last_send = object(), time.monotonic()
            while not await request.is_disconnected():
                job = store.get_job(job_id)
                if job is None:
                    return
                live = runner.progress(job_id)
                out = _job_out(job, runner, live)
                if job["status"] not in ("queued", "running"):
                    yield _sse("end", out)
                    return
                key = (job["status"], live[0] if live else None)
                if key != seen:
                    seen = key
                    yield _sse("progress", out)
                    last_send = time.monotonic()
                elif time.monotonic() - last_send >= _KEEPALIVE_S:
                    yield ": keep-alive\n\n"
                    last_send = time.monotonic()
                await asyncio.sleep(_POLL_S)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers=_SSE_HEADERS)

    @router.get("/jobs/{job_id}/result")
    def get_result(job_id: str):
        job_or_404(job_id)
        body = store.get_result(job_id)
        if body is None:
            raise HTTPException(404, "no result")
        return body

    @router.post("/jobs/{job_id}/cancel", status_code=202)
    def cancel_job(job_id: str):
        job_or_404(job_id)
        if not runner.cancel(job_id):
            raise HTTPException(409, "job is not queued or running")
        return {}

    @router.post("/jobs/{job_id}/resume", status_code=201)
    def resume_job(job_id: str):
        job = job_or_404(job_id)
        if job["status"] not in _RESUMABLE:
            raise HTTPException(409, f"cannot resume a {job['status']} job")
        return _submit(runner, job["kind"], job["request"])

    @router.delete("/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str):
        if job_or_404(job_id)["status"] in ("queued", "running"):
            raise HTTPException(409, "job is queued or running; cancel it first")
        store.delete_job(job_id)
        return Response(status_code=204)

    app.include_router(auth_router)
    app.include_router(router)
    return app
