"""FastAPI app factory and job routes."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import srmcore
import srmweb
from srmcore.materials.library import available_materials, load_material
from srmcore.materials.schema import SoftMagneticMaterial
from srmcore.model.design import RadialSRMParams
from srmcore.model.errors import InputError
from srmweb.auth import Sessions, auth_router, require_auth
from srmweb.config import Settings
from srmweb.geometry import outline_svg
from srmweb.jobs import KINDS, JobRunner, QueueFull
from srmweb.schemas import JobIn, JobOut
from srmweb.store import ACTIVE, RESUMABLE, Store

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
    return JobOut(**{k: job[k] for k in JobOut.model_fields if k in job},
                  active=job["status"] in ACTIVE, resumable=job["status"] in RESUMABLE)


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

    app = FastAPI(title="srmweb", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        """FastAPI's 422 body, without the job-kind tag that the `JobIn` union puts in `loc`:
        `["body", "payload", ...]` stays the path of a field of a job request."""
        errors = jsonable_encoder(exc.errors())
        for e in errors:
            if e["loc"][:1] == ["body"] and e["loc"][2:3] == ["payload"] and e["loc"][1] in KINDS:
                del e["loc"][1]
        return JSONResponse({"detail": errors}, status_code=422)

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
        if job.kind != "search":
            raise HTTPException(422, "submit through /api/cases/{id}/evaluate or /validate")
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
                if job["status"] not in ACTIVE:
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
        if job["status"] not in RESUMABLE:
            raise HTTPException(409, f"cannot resume a {job['status']} job")
        return _submit(runner, job["kind"], job["request"])

    @router.delete("/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str):
        if job_or_404(job_id)["status"] in ACTIVE:
            raise HTTPException(409, "job is queued or running; cancel it first")
        store.delete_job(job_id)
        return Response(status_code=204)

    @router.post("/geometry")
    def geometry(machine: RadialSRMParams):
        """Motor outline paths. A design that violates a rule gives 422 with FastAPI's
        `{"detail": [{"loc": ["body", parameter], "msg": message, "type": rule}]}`."""
        try:
            return outline_svg(machine)
        except InputError as exc:
            raise HTTPException(422, [
                {"loc": ["body", i.parameter], "msg": i.message, "type": i.rule}
                for i in exc.issues if i.severity == "error"]) from exc

    @router.get("/materials")
    def materials():
        out = []
        for name in available_materials():
            m = load_material(name)
            if isinstance(m, SoftMagneticMaterial):
                out.append({"name": m.name, "grade": m.confidence,
                            "thickness_mm": None if m.thickness is None else m.thickness * 1000,
                            "js": m.saturation_polarisation})
        return out

    def cache_files():
        return list(settings.cache_dir.glob("*.h5")) if settings.cache_dir.is_dir() else []

    @router.get("/settings/cache")
    def cache_info():
        files = cache_files()
        return {"path": str(settings.cache_dir), "files": len(files),
                "bytes": sum(f.stat().st_size for f in files)}

    @router.delete("/settings/cache", status_code=204)
    def clear_cache():
        if runner.busy():
            raise HTTPException(409, "a job is running; wait for it or cancel it")
        for f in cache_files():
            f.unlink(missing_ok=True)
        return Response(status_code=204)

    @router.get("/openapi.json", include_in_schema=False)
    def openapi_json():
        return app.openapi()

    @router.get("/docs", include_in_schema=False)
    def swagger():
        return get_swagger_ui_html(openapi_url="/api/openapi.json", title="srmweb API")

    app.include_router(auth_router)
    app.include_router(router)
    _mount_frontend(app, settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        def not_built():
            return PlainTextResponse("Frontend not built: cd web && npm ci && npm run build")
        return
    root = static_dir.resolve()
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
