"""FastAPI app factory and job routes."""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
import re
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from scipy.io import savemat

import srmcore
import srmweb
import srmapp
from srmapp import field
from srmapp.case import LIMIT_FIELDS, CaseInputs, reference_design
from srmapp.losses import N_ANGLES, check_loss_data
from srmapp.report import findings
from srmapp.sizing.estimates import active_mass
from srmapp.sizing.generator import REFERENCE_TURNS
from srmapp.references import REFERENCES
from srmcore.materials.library import available_materials, load_material
from srmcore.materials.loss import MissingLossData
from srmcore.materials.schema import SoftMagneticMaterial
from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials
from srmcore.model.errors import InputError
from srmcore.topology.dxf_io import import_dxf, write_dxf
from srmsil import build as sil_build, run as sil_run, tables as sil_tables
from srmsil.hil import HilError
from srmsil.hil.config import check_isr_rate
from srmsil.hil.transport import Transport
from srmweb.auth import Sessions, auth_router, require_auth
from srmweb.cases import check_case, estimate as estimate_case, losses_estimate, resolved_margin
from srmweb.config import Settings, is_loopback
from srmweb.frames import FieldContext, b_task, frame_task, mesh_task, pack
from srmweb.geometry import outline_svg
from srmweb.hil import POLL_S as HIL_POLL_S, HilManager, check_loopback, serial_transports, sil_t0
from srmweb.jobs import CUSTOM_REFUSED, KINDS, JobRunner, QueueFull, lane_of
from srmweb.quick import LaneTimeout
from srmweb.results import (BWaveformOut, CaseOut, DxfImportOut, CaseSummaryOut, FindingOut, LossesOut,
                            MaterialOut, ReferenceOut, ReportOut, SearchResultOut)
from srmweb.schemas import (AnimateIn, AnimateRequest, CandidateCase, CasePatch, CompareOut, ControlIn, ControlRequest,
                            ComparisonOut, ControllerOut, EditCase, EstimateOut, EvaluateBody, EvaluateRequest, FieldIn,
                            HilCaptureIn, HilCaptureOut, HilCommandIn, HilFlashIn, HilFlashRequest, HilFlashResultOut, HilOpenIn,
                            HilParamIn, HilParamOut, HilSessionOut, IssuesOut,
                            JobCreated, JobIn, JobOut, LossesBody, LossesEstimateOut, LossesRequest, MotorIn,
                            ReferenceCase, TargetCheckIn, TargetCheckOut, ValidateIn, ValidateRequest)
from srmweb.setup import (NO_MACHINE_MATERIALS, ImportCase, SetupFile, case_inputs_from_setup,
                          setup_from_case, setup_loc)
from srmweb.serialize import to_json
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


DXF_MAX_BYTES = 10 * 1024 * 1024


def _file_name(label: str) -> str:
    """`label` as a header-safe file name stem."""
    return re.sub(r"[^A-Za-z0-9 ._()+-]", "", label.replace("/", "-")).strip() or "case"


def _evaluated_since_0_6(evaluation: dict) -> bool:
    """False for an evaluation without a recorded srmapp version or made by one below 0.6.0 (its winding
    resistance was made at 100 °C without the drive tail)."""
    version = evaluation.get("srmapp_version")
    try:
        return version is not None and tuple(int(x) for x in version.split(".")[:2]) >= (0, 6)
    except ValueError:
        return False


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
                  active=job["status"] in ACTIVE, resumable=job["status"] in RESUMABLE,
                  lane=lane_of(job["kind"]),
                  queue_position=runner.queue_position(job["id"]) if job["status"] == "queued" else None)


def _submit(runner: JobRunner, kind: str, request: dict) -> dict:
    try:
        return {"id": runner.submit(kind, request)}
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc


def create_app(settings: Settings,
               runner_factory: Callable[[Store, Settings], JobRunner] = JobRunner,
               hil_transports: Callable[[], tuple[Transport, Transport]] | None = None) -> FastAPI:
    """`hil_transports` opens the (emulator, controller) links of the HIL rig; the default finds the boards' USB
    serial ports."""
    store = Store(settings.db)
    runner = runner_factory(store, settings)

    def flash_active() -> bool:
        return any(j["kind"] == "hil_flash" and j["status"] in ACTIVE for j in store.list_jobs())

    def flashed_hash(case_id: str, controller: str) -> int | None:
        """The firmware hash of the newest finished Build & Flash job of the case and controller."""
        for j in store.list_jobs():
            if j["kind"] == "hil_flash" and j["status"] == "done":
                r = store.get_result(j["id"]) or {}
                if r.get("case_id") == case_id and r.get("controller") == controller and "firmware_hash" in r:
                    return r["firmware_hash"]
        return None

    hil = HilManager(settings, hil_transports or serial_transports, flash_active, flashed_hash)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runner.start()
        yield
        if is_loopback(settings.host):
            hil.close()
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

    app.state.settings, app.state.store, app.state.runner, app.state.hil = settings, store, runner, hil
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
                # the whole second of the elapsed time is part of the key, so the clock ticks between progress reports
                key = (job["status"], live[0] if live else None, int(live[1]["elapsed_s"]) if live else None)
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
        if job["kind"] == "control":
            controller_folders(job["request"]["controller"])
        if job["kind"] == "hil_flash":
            check_loopback(settings)
            with hil.gate:
                if hil.is_open():
                    raise HTTPException(409, "close the HIL session before flashing")
                return _submit(runner, job["kind"], job["request"])
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

    def evaluated_inputs(case_id: str) -> CaseInputs | JSONResponse:
        """The inputs of an evaluated case with a winding; 409 for a draft or a stale case, 422 for inputs that fail
        the case check."""
        case = case_or_404(case_id)
        evaluation = None if case["stale"] else store.case_result(case_id, "evaluate")
        if evaluation is None or evaluation.get("status") != "ok" or not evaluation.get("winding"):
            raise HTTPException(409, "evaluate this case first")
        inputs, errors, warnings = check_case(case["inputs"])
        return _invalid(errors, warnings) if inputs is None else inputs

    @router.post("/cases/{case_id}/losses", status_code=201, response_model=JobCreated)
    def losses_job(case_id: str, body: LossesBody | None = None):
        inputs = evaluated_inputs(case_id)
        if isinstance(inputs, JSONResponse):
            return inputs
        if not _evaluated_since_0_6(store.case_result(case_id, "evaluate")):
            raise HTTPException(409, "evaluation made before 0.6.0 — re-evaluate the case")
        try:
            check_loss_data(inputs.design)
        except MissingLossData as exc:
            return _invalid([{"loc": ["design", "machine", "materials"], "msg": str(exc)}], [])
        idle_or_409(case_id)
        body = body or LossesBody()
        request = LossesRequest(case_id=case_id, inputs=inputs, **body.model_dump())
        return {"job_id": _submit(runner, "losses", request.model_dump(mode="json"))["id"]}

    @router.get("/cases/{case_id}/losses", response_model=LossesOut)
    def get_losses(case_id: str):
        case_or_404(case_id)
        result = store.case_result(case_id, "losses")
        if result is None or result.get("cancelled"):
            raise HTTPException(404, "no losses for this case")
        return result

    @router.get("/cases/{case_id}/losses/estimate", response_model=LossesEstimateOut)
    def losses_estimate_route(case_id: str, n_speeds: Annotated[int, Query(ge=2, le=12)] = 6,
                              n_torques: Annotated[int, Query(ge=1, le=10)] = 5):
        inputs, errors, warnings = check_case(case_or_404(case_id)["inputs"])
        if inputs is None:
            return _invalid(errors, warnings)
        return losses_estimate(inputs, store, n_speeds, n_torques)

    @router.get("/cases/{case_id}/losses/b", response_model=BWaveformOut)
    def losses_b(case_id: str, point: int, x: float, y: float):
        """B(t) in the lamination at the iron element nearest (x, y) metres (stator frame, rotor at angle 0) for
        operating point `point`, from the cached stroke."""
        case = case_or_404(case_id)
        result = store.case_result(case_id, "losses")
        if result is None or result.get("cancelled") or not 0 <= point < len(result["points"]):
            raise HTTPException(404, "no such operating point")
        op = result["points"][point]
        if not op["reached"] or not op["stroke_key"]:
            raise HTTPException(404, "this operating point was not reached")
        if not (settings.cache_dir / "strokes" / f"{op['stroke_key']}.npz").is_file():
            raise HTTPException(410, "the stroke fields were cleared; run the losses again")
        design = reference_design(CaseInputs.model_validate(case["inputs"]))
        try:
            return to_json(runner.quick.run(b_task, design, op["stroke_key"], N_ANGLES, op["speed_rpm"], x, y,
                                            settings.cache_dir))
        except FileNotFoundError as exc:
            raise HTTPException(410, "the stroke fields were cleared; run the losses again") from exc
        except LaneTimeout as exc:
            raise HTTPException(504, "the lookup took longer than 120 s") from exc
        except Exception as exc:
            raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

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

    def field_context(case_id: str) -> FieldContext:
        case = case_or_404(case_id)
        evaluation = None if case["stale"] else store.case_result(case_id, "evaluate")
        if evaluation is None or evaluation.get("status") != "ok" or not evaluation.get("winding"):
            raise HTTPException(409, "evaluate this case first")
        inputs = CaseInputs.model_validate(case["inputs"])
        w = evaluation["winding"]
        return FieldContext(reference_design(inputs), inputs, w["turns"] / (w["paths"] * REFERENCE_TURNS),
                            evaluation["key"]["i_max"], w["current"])

    def limited_context(case_id: str, current_a: float) -> FieldContext:
        ctx = field_context(case_id)
        if current_a > 2 * ctx.i_max:
            raise HTTPException(422, "current above twice the map's top current")
        return ctx

    def quick_run(fn, *args):
        try:
            return runner.quick.run(fn, *args)
        except LaneTimeout as exc:
            raise HTTPException(504, "the field solve took longer than 120 s") from exc
        except Exception as exc:
            raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    def binary(meta: dict, arrays: dict) -> Response:
        return Response(pack(to_json(meta), arrays), media_type="application/octet-stream")

    @router.get("/cases/{case_id}/field/mesh")
    def field_mesh_route(case_id: str):
        ctx = field_context(case_id)
        mesh = quick_run(mesh_task, ctx.design, settings.cache_dir)
        key = store.case_result(case_id, "evaluate")["key"]
        meta = {"n_stator_nodes": mesh.n_stator_nodes, "regions": [r.__dict__ for r in mesh.regions],
                "b_last": mesh.b_last, "n_rotor_poles": ctx.inputs.design.machine.n_rotor_poles,
                "aligned_angle": key["aligned_angle"], "unaligned_angle": key["unaligned_angle"],
                "winding_current": ctx.winding_current, "i_max": ctx.i_max}
        return binary(meta, {
            "nodes": mesh.nodes.astype(np.float32), "triangles": mesh.triangles.astype(np.uint32),
            "region": mesh.region.astype(np.uint8),
            **{f"probe.{z}": mesh.probes[z].astype(np.uint32) for z in ("stator_pole", "stator_yoke", "rotor_pole")}})

    @router.post("/cases/{case_id}/field")
    def field_snapshot(case_id: str, body: FieldIn):
        ctx = limited_context(case_id, body.current_a)
        frame = quick_run(frame_task, ctx.design, body.angle, body.current_a * ctx.k, settings.cache_dir)
        meta = {"angle": body.angle, "current_a": body.current_a, "psi": frame.psi * ctx.k,
                "torque": frame.torque, "status": frame.status, "probes": frame.probes}
        return binary(meta, {"band": frame.band.astype(np.uint32), "b": frame.b.astype(np.float32),
                             "a": frame.a.astype(np.float32)})

    @router.post("/cases/{case_id}/animate", status_code=201, response_model=JobCreated)
    def animate_case(case_id: str, body: AnimateIn):
        ctx = limited_context(case_id, body.current_a)
        request = AnimateRequest(case_id=case_id, inputs=ctx.inputs, current_a=body.current_a,
                                 coil_current=body.current_a * ctx.k, k=ctx.k, frames=body.frames)
        return {"job_id": _submit(runner, "animate", request.model_dump(mode="json"))["id"]}

    def cached_frames(job: dict, result: dict) -> list:
        """The cached frame of every angle of an animate job's result (None for a cleared frame)."""
        request = AnimateRequest.model_validate(job["request"])
        design = reference_design(request.inputs)
        return [field.cached_frame(design, angle, request.coil_current, cache_dir=settings.cache_dir)
                for angle in result["angles"]]

    def frames_cached(job: dict) -> bool:
        """True when the animate job's result exists and all its frames are still cached."""
        result = store.get_result(job["id"])
        if result is None or result.get("cancelled"):
            return False
        try:
            return all(f is not None for f in cached_frames(job, result))
        except (ValidationError, InputError):
            return False

    @router.get("/jobs/{job_id}/frames")
    def job_frames(job_id: str):
        job = job_or_404(job_id)
        result = store.get_result(job_id) if job["kind"] == "animate" else None
        if result is None or result.get("cancelled"):
            raise HTTPException(404, "no frames")
        frames = cached_frames(job, result)
        if any(f is None for f in frames):
            raise HTTPException(410, "the frames were cleared; animate again")
        arrays = {}
        for n, f in enumerate(frames):
            arrays |= {f"band.{n}": f.band.astype(np.uint32), f"b.{n}": f.b.astype(np.float32),
                       f"a.{n}": f.a.astype(np.float32)}
        return binary(result, arrays)

    def motor_json(motor: sil_tables.MotorData) -> dict:
        return {"angles": motor.angles.tolist(), "currents": motor.currents.tolist(), "psi": motor.psi.tolist(),
                "torque": motor.torque.tolist(), "resistance": motor.resistance, "n_phases": motor.n_phases,
                "n_rotor_poles": motor.n_rotor_poles, "bus_voltage": motor.bus_voltage}

    def control_motor(case_id: str, bus_voltage: float | None = None) -> sil_tables.MotorData:
        """The case's map and winding as simulator motor data; 409 unless the case is evaluated."""
        field_context(case_id)
        case = case_or_404(case_id)
        evaluation = store.case_result(case_id, "evaluate")
        bus = bus_voltage or CaseInputs.model_validate(case["inputs"]).requirements.bus_voltage_v
        try:
            motor = sil_tables.motor_data_from_json(evaluation, bus)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not (np.isfinite(motor.psi).all() and np.isfinite(motor.torque).all()):
            raise HTTPException(409, "the map has non-finite points")
        return motor

    def controller_folders(controller: str) -> list[Path]:
        """The folders a controller compiles from; 403 off loopback for a custom folder, 422 if it is invalid."""
        if controller in sil_run.REFERENCE:
            folder = sil_run.controller_dir(controller)
            return [folder, folder.parent / "common"]
        if not is_loopback(settings.host):
            raise HTTPException(403, CUSTOM_REFUSED)
        if not Path(controller).is_absolute():
            raise HTTPException(422, "a custom controller must be an absolute folder path")
        try:
            folder = sil_run.controller_dir(controller)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return [folder]

    @router.post("/cases/{case_id}/control", status_code=201, response_model=JobCreated)
    def control_case(case_id: str, body: ControlIn):
        motor = control_motor(case_id, body.scenario.bus_voltage)
        controller_folders(body.controller)
        request = ControlRequest(case_id=case_id, motor=MotorIn(**motor_json(motor)), controller=body.controller,
                                 scenario=body.scenario)
        return {"job_id": _submit(runner, "control", request.model_dump(mode="json"))["id"]}

    def traces_arrays(res: sil_run.SimResult, n_px: int, prefix: str = "",
                      span: tuple[float, float] | None = None) -> dict:
        """Every trace of a run decimated to n_px buckets as `t.<prefix><name>[.<phase>]` and `y.<prefix>...`,
        restricted to the samples with span[0] <= t <= span[1] when a span is given."""
        if not res.traces:
            return {}
        t_all = res.traces["t"]
        keep = slice(None) if span is None else (t_all >= span[0] - 1e-12) & (t_all <= span[1] + 1e-12)
        arrays = {}
        for name, trace in res.traces.items():
            if name == "t":
                continue
            for k, y in (enumerate(trace) if trace.ndim == 2 else [(None, trace)]):
                label = prefix + (name if k is None else f"{name}.{k}")
                t, y = sil_run.decimate(t_all[keep], y[keep], n_px)
                arrays[f"t.{label}"], arrays[f"y.{label}"] = t.astype(np.float32), y.astype(np.float32)
        return arrays

    @router.get("/jobs/{job_id}/control")
    def job_control(job_id: str, n_px: Annotated[int, Query(ge=100, le=10000)] = 1500):
        job = job_or_404(job_id)
        result = store.get_result(job_id) if job["kind"] == "control" and job["status"] == "done" else None
        if result is None:
            raise HTTPException(404, "no control run")
        run_file = Path(result["run_file"])
        if not run_file.is_file():
            raise HTTPException(410, "the run was cleared; run the controller again")
        res = sil_run.load(run_file)
        arrays = traces_arrays(res, n_px)
        meta = {"summary": result["summary"], "scenario": res.scenario.model_dump(mode="json"),
                "controller": res.controller, "n_phases": res.traces["i"].shape[0]}
        return binary(meta, arrays)

    @router.get("/cases/{case_id}/control/header")
    def control_header(case_id: str):
        motor = control_motor(case_id)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "srm_motor_tables.h"
            try:
                sil_tables.write_header(motor, sil_tables.ctrl_tables(motor), path)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            text = path.read_text()
        return Response(text, media_type="text/x-c",
                        headers={"Content-Disposition": 'attachment; filename="srm_motor_tables.h"'})

    @router.post("/control/target-check", response_model=TargetCheckOut)
    def control_target_check(body: TargetCheckIn):
        motor = control_motor(body.case_id)
        folders = controller_folders(body.controller)
        c_dir = Path(sil_run.__file__).parent / "c"
        with tempfile.TemporaryDirectory() as tmp:
            try:
                sil_tables.write_header(motor, sil_tables.ctrl_tables(motor), Path(tmp) / "srm_motor_tables.h")
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            sources = [s for f in folders for s in sil_build.controller_sources(f)]
            check = sil_build.target_check(sources, [c_dir, Path(tmp), *folders])
        return {"ok": check.ok, "compiler": check.compiler, "log": check.log}

    @router.get("/control/controllers", response_model=list[ControllerOut])
    def control_controllers():
        return [{"name": name, "params": [{"name": n, "unit": u, "default": d} for n, u, d in params]}
                for name, params in sil_run.PARAMS.items()]

    def case_machine(case: dict) -> RadialSRMParams | JSONResponse:
        """The case's machine, or the 422 response for inputs that fail the case check."""
        inputs, errors, warnings = check_case(case["inputs"])
        return _invalid(errors, warnings) if inputs is None else inputs.design.machine

    @router.get("/cases/{case_id}/dxf")
    def dxf_export(case_id: str):
        case = case_or_404(case_id)
        machine = case_machine(case)
        if isinstance(machine, JSONResponse):
            return machine
        return Response(write_dxf(machine), media_type="application/dxf",
                        headers={"Content-Disposition": f'attachment; filename="{_file_name(case["label"])}.dxf"'})

    @router.post("/cases/{case_id}/dxf", status_code=201, response_model=DxfImportOut)
    def dxf_import(case_id: str, file: Annotated[UploadFile, File()]):
        parent = case_or_404(case_id)
        data = file.file.read(DXF_MAX_BYTES + 1)
        if len(data) > DXF_MAX_BYTES:
            raise HTTPException(413, "the DXF file is larger than 10 MB")
        machine = case_machine(parent)
        if isinstance(machine, JSONResponse):
            return machine
        iron, issues = import_dxf(data, machine)
        found = [{"loc": ["iron"], "msg": f"[{i.rule}] {i.message}"} for i in issues]
        if iron is None:
            return _invalid([e for e, i in zip(found, issues) if i.severity == "error"],
                            [e for e, i in zip(found, issues) if i.severity != "error"])
        inputs = {**parent["inputs"], "design": {**parent["inputs"]["design"], "machine": {
            **parent["inputs"]["design"]["machine"], "iron": iron.model_dump(mode="json")}}}
        new = store.create_case(origin="dxf", inputs=inputs, label=f"DXF edit of {parent['label']}",
                                parent_case_id=parent["id"], stale=True)
        return DxfImportOut(case=case_out(store.get_case(new)), warnings=found)

    def compare_rows(case: dict) -> list[dict] | None:
        """Before/after rows against the case's parent, None for a case without a parent."""
        if case["parent_case_id"] is None:
            return None
        parent = case_or_404(case["parent_case_id"])

        def column(c: dict) -> list[float | None]:
            ev = store.case_result(c["id"], "evaluate")
            key = (ev or {}).get("key")
            if not key:
                return [None] * 7
            try:
                mass = active_mass(reference_design(CaseInputs.model_validate(c["inputs"])).machine)
            except (ValidationError, InputError):
                return [None] * 7
            # exact iron of the case's own design plus the copper of the winding the evaluation chose
            total = mass.iron + ev["winding"]["copper_mass"] if ev.get("winding") else None
            return [key["la"] * 1e3, key["lu"] * 1e3, key["peak_torque"], key["psi_max"],
                    mass.stator_iron, mass.rotor_iron, total]

        before, after = column(parent), column(case)
        names = [("La", "mH"), ("Lu", "mH"), ("Peak torque", "N·m"), ("Flux linkage max", "Wb"),
                 ("Stator iron", "kg"), ("Rotor iron", "kg"), ("Total mass", "kg")]
        return [{"name": n, "unit": u, "before": b, "after": a} for (n, u), b, a in zip(names, before, after)]

    @router.get("/cases/{case_id}/compare", response_model=CompareOut)
    def compare(case_id: str):
        case = case_or_404(case_id)
        rows = compare_rows(case)
        if rows is None:
            raise HTTPException(404, "this case has no parent to compare with")
        return CompareOut(parent_id=case["parent_case_id"], parent_evaluated=rows[0]["before"] is not None, rows=rows)

    @router.get("/cases/{case_id}/report", response_model=ReportOut)
    def report(case_id: str):
        case = case_or_404(case_id)
        evaluation = store.case_result(case_id, "evaluate")
        if evaluation is None:
            raise HTTPException(409, "the case has no evaluation")
        losses = store.case_result(case_id, "losses")
        if losses is not None and losses.get("cancelled"):
            losses = None
        animate = [j for j in store.case_jobs(case_id) if j["kind"] == "animate" and j["status"] == "done"
                   and not (store.get_result(j["id"]) or {"cancelled": True}).get("cancelled")]
        chosen = next((j for j in animate if frames_cached(store.get_job(j["id"]))), None)
        missing = (None if chosen else "no animation run" if not animate
                   else "the frames were cleared from the cache; animate again")
        validation = store.case_result(case_id, "validate")
        if validation is not None and validation.get("cancelled"):
            validation = None
        found = findings(CaseInputs.model_validate(case["inputs"]), evaluation, validation,
                         losses, compare_rows(case) if case["origin"] == "dxf" and store.get_case(case["parent_case_id"] or "") else None, missing)
        return ReportOut(
            findings=[FindingOut(**vars(f)) for f in found],
            versions={"srmcore": srmcore.__version__, "srmapp": srmapp.__version__, "srmweb": srmweb.__version__},
            generated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            animation_job_id=chosen["id"] if chosen else None,
            animation_current_a=store.get_result(chosen["id"])["current_a"] if chosen else None)

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
        if not settings.cache_dir.is_dir():
            return []
        sil = settings.cache_dir / "sil"
        found = [*settings.cache_dir.glob("*.h5"),
                 *(f for sub in ("fields", "strokes") for f in (settings.cache_dir / sub).glob("*.npz")),
                 *(sil / "runs").glob("*.npz"), *(sil / "runs").glob("*.json"), *(sil / "build").glob("*"),
                 *(sil / "hil").rglob("*")]
        return [f for f in found if f.is_file() and ".tmp." not in f.name]

    @router.get("/settings/cache")
    def cache_info():
        files = cache_files()
        return {"path": str(settings.cache_dir), "files": len(files),
                "bytes": sum(f.stat().st_size for f in files)}

    @router.delete("/settings/cache", status_code=204)
    def clear_cache():
        if runner.busy() or runner.busy("quick") or runner.quick.busy():
            raise HTTPException(409, "a job is running; wait for it or cancel it")
        if hil.is_open():
            raise HTTPException(409, "a HIL session is open; close it first")
        if hil.comparing():
            raise HTTPException(409, "a HIL comparison is running; wait for it")
        for f in cache_files():
            f.unlink(missing_ok=True)
        return Response(status_code=204)

    @router.get("/openapi.json", include_in_schema=False)
    def openapi_json():
        return app.openapi()

    @router.get("/docs", include_in_schema=False)
    def swagger():
        return get_swagger_ui_html(openapi_url="/api/openapi.json", title="srmweb API")

    hil_router = APIRouter(prefix="/api", dependencies=[Depends(require_auth),
                                                        Depends(lambda: check_loopback(settings))])

    def hil_setup(case_id: str, body: HilFlashIn) -> sil_tables.MotorData:
        """The case's motor for a HIL setup; 409 unless the case is evaluated, 422 for an invalid controller folder or
        an ISR rate the HIL cannot sample at."""
        motor = control_motor(case_id, body.scenario.bus_voltage)
        controller_folders(body.controller)
        try:
            check_isr_rate(body.scenario)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return motor

    @hil_router.post("/cases/{case_id}/hil/flash", status_code=201, response_model=JobCreated)
    def hil_flash(case_id: str, body: HilFlashIn):
        motor = hil_setup(case_id, body)
        request = HilFlashRequest(case_id=case_id, motor=MotorIn(**motor_json(motor)), controller=body.controller,
                                  scenario=body.scenario, modes=body.modes)
        with hil.gate:
            if hil.is_open():
                raise HTTPException(409, "close the HIL session before flashing")
            return {"job_id": _submit(runner, "hil_flash", request.model_dump(mode="json"))["id"]}

    @hil_router.get("/jobs/{job_id}/hil-flash", response_model=HilFlashResultOut)
    def hil_flash_result(job_id: str):
        """The build log and firmware hash of a finished Build & Flash job."""
        job = job_or_404(job_id)
        result = store.get_result(job_id) if job["kind"] == "hil_flash" and job["status"] == "done" else None
        if result is None:
            raise HTTPException(404, "no flash result")
        return result

    @hil_router.post("/hil/session", status_code=201, response_model=HilSessionOut)
    def hil_open(body: HilOpenIn):
        motor = control_motor(body.case_id, body.scenario.bus_voltage)
        controller_folders(body.controller)
        return hil.open(body.case_id, body, motor)

    @hil_router.delete("/hil/session", status_code=204)
    def hil_close():
        hil.close()
        return Response(status_code=204)

    @hil_router.get("/hil/session/events")
    async def hil_events(request: Request):
        """Live statistics of both boards (`event: live`, data `{session, emu, ctrl}`), polled at 20 Hz and sent when
        they change; `event: end` once the session is closed, `event: link_lost` (data `{error}`) when a board link fails."""
        if not hil.is_open():
            raise HTTPException(409, "no HIL session is open")

        async def stream():
            seen, last_send = None, time.monotonic()
            while not await request.is_disconnected():
                try:
                    event = await asyncio.to_thread(hil.poll)
                except HilError as exc:
                    yield f"event: link_lost\ndata: {json.dumps({'error': str(exc)})}\n\n"
                    return
                if event is None:
                    yield "event: end\ndata: {}\n\n"
                    return
                if event != seen:
                    seen = event
                    yield f"event: live\ndata: {json.dumps(event)}\n\n"
                    last_send = time.monotonic()
                elif time.monotonic() - last_send >= _KEEPALIVE_S:
                    yield ": keep-alive\n\n"
                    last_send = time.monotonic()
                await asyncio.sleep(HIL_POLL_S)

        return StreamingResponse(stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    @hil_router.post("/hil/session/param", response_model=HilParamOut, response_model_exclude_none=True)
    def hil_param(body: HilParamIn):
        return hil.param(body.name, body.value)

    @hil_router.post("/hil/session/command", response_model=HilSessionOut)
    def hil_command(body: HilCommandIn):
        return hil.command(body.mode, body.value)

    @hil_router.post("/hil/session/start", response_model=HilSessionOut)
    def hil_start():
        return hil.start()

    @hil_router.post("/hil/session/stop", response_model=HilSessionOut)
    def hil_stop():
        return hil.stop()

    @hil_router.post("/hil/session/capture", status_code=201, response_model=HilCaptureOut)
    def hil_capture(body: HilCaptureIn):
        return hil.capture(body.n_steps)

    @hil_router.get("/hil/captures/{capture_id}")
    def hil_capture_traces(capture_id: str, n_px: Annotated[int, Query(ge=100, le=10000)] = 1500):
        """The capture's traces decimated to n_px buckets (`t.<trace>`, `y.<trace>`), and once compared the matched
        SIL run's over the capture's time span (`t.sil.<trace>`, `y.sil.<trace>`)."""
        path = hil.capture_file(capture_id)
        res = sil_run.load(path)
        arrays = traces_arrays(res, n_px)
        sil_file = path.with_name(f"{capture_id}.sil.npz")
        sil = sil_run.load(sil_file) if sil_file.is_file() else None
        t0 = sil_t0(sil) if sil is not None else None
        compared = t0 is not None                  # a SIL file without its start time counts as not compared
        if compared and res.traces:
            sil = replace(sil, traces={**sil.traces, "t": sil.traces["t"] + t0})   # the capture's time base
            t = res.traces["t"]
            arrays |= traces_arrays(sil, n_px, "sil.", (float(t[0]), float(t[-1])))
        meta = {"summary": res.summary, "scenario": res.scenario.model_dump(mode="json"), "controller": res.controller,
                "hil": res.hil, "compared": compared, "n_phases": len(res.summary.i_rms)}
        return binary(meta, arrays)

    @hil_router.get("/hil/captures/{capture_id}/compare", response_model=ComparisonOut)
    def hil_compare(capture_id: str):
        return hil.compare(capture_id, control_motor)

    app.include_router(auth_router)
    app.include_router(router)
    app.include_router(hil_router)
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
