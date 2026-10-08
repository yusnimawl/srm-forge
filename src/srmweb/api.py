"""FastAPI app factory and job routes."""
from __future__ import annotations

import asyncio
import io
import re
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from scipy.io import savemat

import srmcore
import srmweb
from srmapp.case import LIMIT_FIELDS, CaseInputs
from srmapp.references import REFERENCES
from srmcore.materials.library import available_materials, load_material
from srmcore.materials.schema import SoftMagneticMaterial
from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials
from srmcore.model.errors import InputError
from srmweb.auth import Sessions, auth_router, require_auth
from srmweb.cases import check_case, estimate as estimate_case, resolved_margin
from srmweb.config import Settings
from srmweb.geometry import outline_svg
from srmweb.jobs import KINDS, JobRunner, QueueFull
from srmweb.results import CaseOut, CaseSummaryOut, MaterialOut, ReferenceOut, SearchResultOut
from srmweb.schemas import (CandidateCase, CasePatch, EditCase, EstimateOut,
                            EvaluateBody, EvaluateRequest, IssuesOut, JobCreated, JobIn, JobOut, ReferenceCase,
                            ValidateIn, ValidateRequest)
from srmweb.setup import (NO_MACHINE_MATERIALS, ImportCase, SetupFile, case_inputs_from_setup,
                          setup_from_case, setup_loc)
from srmweb.store import ACTIVE, RESUMABLE, Store

_POLL_S = 0.5
_KEEPALIVE_S = 15.0
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
MAX_SHOWN_CASES = 6
CaseCreate = Annotated[CandidateCase | ReferenceCase | EditCase | ImportCase, Field(discriminator="origin")]
_EVALUATED = ("status", "torque_ratio", "power_ratio", "peak_power_w", "mass_kg",
              "power_density_kw_per_kg", "efficiency_base", "feasible")


def _dig(obj, *keys):
    """`obj[k1][k2]...`, or None where a draft's inputs lack a level."""
    for k in keys:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _summary(case: dict, evaluation: dict | None, validation: dict | None) -> dict:
    inputs = case["inputs"]
    ns, nr = (_dig(inputs, "design", "machine", k) for k in ("n_stator_poles", "n_rotor_poles"))
    return {k: v for k, v in case.items() if k not in ("inputs", "job_id")} | {
        "preset": _dig(inputs, "design", "mesh", "preset"),
        "poles": f"{ns}/{nr}" if isinstance(ns, int) and isinstance(nr, int) else None,
        **{k: (evaluation or {}).get(k) for k in _EVALUATED},
        "validated": bool(validation and validation.get("label"))}


def _file_name(label: str) -> str:
    """`label` as a header-safe file name stem."""
    return re.sub(r"[^A-Za-z0-9 ._()+-]", "", label.replace("/", "-")).strip() or "case"


def _invalid(errors: list[dict], warnings: list[dict]) -> JSONResponse:
    return JSONResponse({"errors": errors, "warnings": warnings}, status_code=422)


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

    app = FastAPI(title="srmweb", version=srmweb.__version__, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        """On `/api/jobs`, FastAPI's 422 body without the job-kind tag that the `JobIn` union puts in
        `loc`: `["body", "payload", ...]` stays the path of a field of a job request."""
        if request.url.path != "/api/jobs":
            return await request_validation_exception_handler(request, exc)
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

    @router.get("/jobs/{job_id}/result", response_model=SearchResultOut)
    def get_result(job_id: str):
        if job_or_404(job_id)["kind"] != "search":
            raise HTTPException(404, "no result")
        body = store.get_result(job_id)
        if body is None:
            raise HTTPException(404, "no result")
        return body

    @router.post("/jobs/{job_id}/cancel", status_code=202)
    def cancel_job(job_id: str):
        job = job_or_404(job_id)
        if job["kind"] == "validate" and job["status"] == "running":
            raise HTTPException(409, "EM validation cannot be cancelled once started")
        if not runner.cancel(job_id):
            raise HTTPException(409, "job is not queued or running")
        return {}

    @router.post("/jobs/{job_id}/resume", status_code=201)
    def resume_job(job_id: str):
        job = job_or_404(job_id)
        if job["status"] not in RESUMABLE:
            raise HTTPException(409, f"cannot resume a {job['status']} job")
        if job["kind"] != "search":
            case = store.get_case(job["request"]["case_id"])
            if case is None:
                raise HTTPException(409, "the job's case was deleted")
            if job["kind"] == "evaluate":
                inputs = check_case(case["inputs"])[0]
                if (not case["stale"] or inputs is None
                        or inputs.model_dump(mode="json") != job["request"]["inputs"]):
                    raise HTTPException(409, "evaluate the case again")
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

    @router.get("/materials", response_model=list[MaterialOut])
    def materials():
        out = []
        for name in available_materials():
            m = load_material(name)
            if isinstance(m, SoftMagneticMaterial):
                out.append({"name": m.name, "grade": m.confidence,
                            "thickness_mm": None if m.thickness is None else m.thickness * 1000,
                            "js": m.saturation_polarisation})
        return out

    @router.get("/references", response_model=list[ReferenceOut])
    def references():
        return [{"name": name, "machine": make()} for name, make in REFERENCES.items()]

    def case_or_404(case_id: str) -> dict:
        case = store.get_case(case_id)
        if case is None:
            raise HTTPException(404, f"no case {case_id}")
        return case

    def idle_or_409(case_id: str) -> None:
        if any(j["status"] in ACTIVE for j in store.case_jobs(case_id)):
            raise HTTPException(409, "a job for this case is still running")

    def case_out(case: dict) -> CaseOut:
        evaluation, validation = (store.case_result(case["id"], k) for k in ("evaluate", "validate"))
        return CaseOut(**_summary(case, evaluation, validation), inputs=case["inputs"],
                       evaluation=evaluation, validation=validation,
                       jobs=[_job_out(j, runner) for j in store.case_jobs(case["id"])])

    def candidate_case(body: CandidateCase) -> str:
        job = job_or_404(body.job_id)
        result = store.get_result(body.job_id) if job["kind"] == "search" else None
        found = [e for e in (result or {}).get("evaluations", []) if e["id"] == body.candidate_id]
        if not found:
            raise HTTPException(404, f"run {body.job_id} has no candidate {body.candidate_id}")
        ev = found[0]
        if ev["status"] != "ok":
            raise HTTPException(409, f"candidate {body.candidate_id} did not evaluate ({ev['status']})")
        request = job["request"]
        inputs = CaseInputs(
            requirements=request["requirements"], design=ev["design"], winding="auto",
            **{k: v for k in LIMIT_FIELDS if (v := request["settings"].get(k)) is not None})
        machine = inputs.design.machine
        case_id = store.create_case(
            origin="candidate", inputs=inputs.model_dump(mode="json"), job_id=body.job_id, stale=True,
            label=f"{machine.n_stator_poles}/{machine.n_rotor_poles} {body.candidate_id}")
        store.attach_evaluation(case_id, body.job_id, ev)
        return case_id

    def reference_case(body: ReferenceCase) -> str:
        material = load_material("10JNEX900")
        machine = REFERENCES[body.name](materials=RegionMaterials(stator=material.name, rotor=material.name),
                                        lamination_thickness=material.thickness)
        inputs = CaseInputs(requirements=body.requirements,
                            design=Design(machine=machine, mesh=MeshSettings(preset=body.preset)))
        return store.create_case(origin="reference", inputs=inputs.model_dump(mode="json"),
                                 label=f"{body.name} reference", stale=True)

    def edit_case(body: EditCase) -> str:
        parent = case_or_404(body.parent_case_id)
        return store.create_case(origin="edit", inputs=body.inputs.model_dump(mode="json"),
                                 label=f"{parent['label']} · edit", parent_case_id=parent["id"], stale=True)

    def import_case(body: ImportCase) -> str | JSONResponse:
        try:
            raw = case_inputs_from_setup(body.setup)
        except ValueError as exc:
            return _invalid([{"loc": [], "msg": str(exc)}], [])
        inputs, errors, warnings = check_case(raw.model_dump(mode="json"))
        if inputs is None:
            return _invalid([{**e, "loc": setup_loc(e["loc"])} for e in errors], warnings)
        return store.create_case(origin="import", inputs=inputs.model_dump(mode="json"),
                                 label="imported setup", stale=True)

    @router.get("/cases", response_model=list[CaseSummaryOut])
    def list_cases():
        return [_summary(c, store.case_result(c["id"], "evaluate"), store.case_result(c["id"], "validate"))
                for c in store.list_cases()]

    @router.post("/cases", status_code=201, response_model=CaseOut)
    def create_case(body: CaseCreate):
        make = {"candidate": candidate_case, "reference": reference_case, "edit": edit_case,
                "import": import_case}[body.origin]
        made = make(body)
        return made if isinstance(made, Response) else case_out(store.get_case(made))

    @router.get("/cases/{case_id}", response_model=CaseOut)
    def get_case(case_id: str):
        return case_out(case_or_404(case_id))

    @router.patch("/cases/{case_id}", response_model=CaseOut)
    def patch_case(case_id: str, body: CasePatch):
        case = case_or_404(case_id)
        fields = body.model_dump(exclude_none=True)
        if "inputs" in fields and not case["stale"]:
            raise HTTPException(409, "evaluated cases are read-only; edit creates a new case")
        if "inputs" in fields:
            idle_or_409(case_id)
        if fields.get("show_in_graphs") and not case["show_in_graphs"]:
            shown = sum(c["show_in_graphs"] for c in store.list_cases() if c["id"] != case_id)
            if shown >= MAX_SHOWN_CASES:
                raise HTTPException(409, f"at most {MAX_SHOWN_CASES} cases can be shown in the graphs")
        store.update_case(case_id, **fields)
        return case_out(store.get_case(case_id))

    @router.post("/validate", response_model=IssuesOut)
    def validate_inputs(body: ValidateIn):
        _, errors, warnings = check_case(body.inputs)
        return {"errors": errors, "warnings": warnings, "margin": resolved_margin(body.inputs)}

    @router.post("/cases/{case_id}/evaluate", status_code=201, response_model=JobCreated)
    def evaluate_case(case_id: str, body: EvaluateBody | None = None):
        case = case_or_404(case_id)
        if not case["stale"]:
            raise HTTPException(409, "case is already evaluated; edit creates a new case")
        idle_or_409(case_id)
        inputs, errors, warnings = check_case(case["inputs"])
        if inputs is None:
            return _invalid(errors, warnings)
        request = EvaluateRequest(case_id=case_id, inputs=inputs, grid=body.grid if body else None)
        return {"job_id": _submit(runner, "evaluate", request.model_dump(mode="json"))["id"]}

    @router.post("/cases/{case_id}/validate", status_code=201, response_model=JobCreated)
    def validate_case_job(case_id: str):
        case = case_or_404(case_id)
        if case["stale"] or store.case_result(case_id, "evaluate") is None:
            raise HTTPException(409, "evaluate this case first")
        inputs, errors, warnings = check_case(case["inputs"])
        if inputs is None:
            return _invalid(errors, warnings)
        if inputs.design.mesh.preset == "screening":
            raise HTTPException(409, "EM validation needs a full map")
        idle_or_409(case_id)
        request = ValidateRequest(case_id=case_id, inputs=inputs)
        return {"job_id": _submit(runner, "validate", request.model_dump(mode="json"))["id"]}

    @router.get("/cases/{case_id}/estimate", response_model=EstimateOut)
    def estimate(case_id: str):
        inputs, errors, warnings = check_case(case_or_404(case_id)["inputs"])
        if inputs is None:
            return _invalid(errors, warnings)
        return estimate_case(inputs, store, settings.cache_dir)

    @router.get("/cases/{case_id}/setup", response_model=SetupFile,
                response_model_exclude=NO_MACHINE_MATERIALS | {"search": True})
    def case_setup(case_id: str, response: Response):
        case = case_or_404(case_id)
        inputs, errors, warnings = check_case(case["inputs"])
        if inputs is None:
            return _invalid(errors, warnings)
        mesh = inputs.design.mesh
        if mesh != MeshSettings(preset=mesh.preset):
            return _invalid([{"loc": ["design", "mesh"],
                              "msg": "custom mesh settings cannot be stored in a setup file"}], warnings)
        response.headers["Content-Disposition"] = f'attachment; filename="{_file_name(case["label"])}.srm-setup.json"'
        return setup_from_case(inputs, case["label"])

    @router.post("/setup/check", response_model=SetupFile, response_model_exclude=NO_MACHINE_MATERIALS)
    def check_setup(setup: SetupFile):
        return setup

    @router.get("/cases/{case_id}/map.mat")
    def map_mat(case_id: str):
        case_or_404(case_id)
        evaluation = store.case_result(case_id, "evaluate") or {}
        grid, winding = evaluation.get("map"), evaluation.get("winding")
        if grid is None or winding is None:
            raise HTTPException(404, "this case has no map; evaluate it first")
        data = {k: np.array(grid[k], dtype=float) for k in ("angles", "currents", "psi", "torque")}
        buffer = io.BytesIO()
        savemat(buffer, data | {"turns": winding["turns"], "paths": winding["paths"]})
        return Response(buffer.getvalue(), media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="case_{case_id[:8]}_map.mat"'})

    @router.delete("/cases/{case_id}", status_code=204)
    def delete_case(case_id: str):
        case_or_404(case_id)
        if any(j["status"] in ACTIVE for j in store.case_jobs(case_id)):
            raise HTTPException(409, "a job of this case is queued or running; cancel it first")
        store.delete_case(case_id)
        return Response(status_code=204)

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
