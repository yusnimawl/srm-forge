"""Case rules of the web layer: the check every route runs on a case's raw inputs, and the run-time estimate.
No HTTP in here; routes turn the answers into responses."""
from __future__ import annotations

import re

from pydantic import ValidationError

from srmapp.case import CaseInputs, map_cache_hit, map_request
from srmcore.model.validator import validate_params
from srmcore.topology.imported import check_iron
from srmweb.schemas import soft_magnetic
from srmweb.store import Store

BUDGET_S = {"screening": 228.0, "full": 1560.0}   # map time when no map of that preset has been timed
SCAN_BUDGET_S = {"auto": 450.0, "fixed": 15.0}    # winding-choice time when none has been timed
_WINDING_FIELD = re.compile(r"^(turns|strands|paths|wire)\b")


def _validation_errors(raw, exc: ValidationError) -> list[dict]:
    """Pydantic's errors with a Fixed winding's field errors at `["winding", field]`: the union adds the branch
    tag `FixedWinding` to their loc and an "Input should be 'auto'" error for the other branch."""
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    if isinstance(raw, dict) and isinstance(raw.get("winding"), dict):
        errors = [e for e in errors if e["loc"][:2] != ["winding", "literal['auto']"]]
        for e in errors:
            if e["loc"][:2] == ["winding", "FixedWinding"]:
                del e["loc"][1]
    return errors


def check_case(raw) -> tuple[CaseInputs | None, list[dict], list[dict]]:
    """Validate a case's raw inputs: the parsed inputs (None when there are errors), the errors and the
    warnings, each `{"loc", "msg"}` with `loc` relative to the inputs."""
    try:
        inputs = CaseInputs.model_validate(raw)
    except ValidationError as exc:
        return None, _validation_errors(raw, exc), []
    errors, warnings = [], []
    for issue in validate_params(inputs.design.machine):
        out = {"loc": ["design", "machine", issue.parameter], "msg": f"[{issue.rule}] {issue.message}"}
        (errors if issue.severity == "error" else warnings).append(out)
    for issue in check_iron(inputs.design.machine):
        out = {"loc": ["design", "machine", "iron"], "msg": f"[{issue.rule}] {issue.message}"}
        (errors if issue.severity == "error" else warnings).append(out)
    if errors:
        return None, errors, warnings
    materials = inputs.design.machine.materials
    for region in ("stator", "rotor"):
        try:
            soft_magnetic(getattr(materials, region))
        except ValueError as exc:
            errors.append({"loc": ["design", "machine", "materials", region], "msg": str(exc)})
    if errors:
        return None, errors, warnings
    try:
        _, _, stage = map_request(inputs)
    except ValueError as exc:
        field = _WINDING_FIELD.match(str(exc)) if inputs.winding != "auto" else None
        return None, [{"loc": ["winding", field[1]] if field else [], "msg": str(exc)}], warnings
    except Exception as exc:   # the check must always answer; the job would fail with the same message
        return None, [{"loc": [], "msg": f"{type(exc).__name__}: {exc}"}], warnings
    if not stage.passes:
        warnings.append({"loc": [], "msg": f"stage 1: {stage.reason}"})
    return inputs, errors, warnings


def resolved_margin(raw) -> float | None:
    """The feasibility margin the inputs imply (an explicit one, or the material-grade rule); None when they do
    not parse or name a material that gives no grade."""
    try:
        return CaseInputs.model_validate(raw).search_settings().resolved_margin
    except Exception:   # a draft may hold anything; check_case reports what is wrong
        return None


def estimate(inputs: CaseInputs, store: Store, cache_dir) -> dict:
    """Seconds an evaluation takes: a new map (if the cache lacks it) plus the winding choice that follows. `basis`
    is "history" when every part comes from timed jobs, else "budget"."""
    new_map = not map_cache_hit(inputs, cache_dir)
    seconds, timed = 0.0, True
    mode = "auto" if inputs.winding == "auto" else "fixed"
    parts = [(store.recent_scan_times(mode), SCAN_BUDGET_S[mode])]
    if new_map:
        preset = inputs.design.mesh.preset
        parts.append((store.recent_map_times(preset), BUDGET_S[preset]))
    for times, budget in parts:
        seconds += sum(times) / len(times) if times else budget
        timed &= bool(times)
    return {"new_map": new_map, "seconds": seconds, "basis": "history" if timed else "budget"}
