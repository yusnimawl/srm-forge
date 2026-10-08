"""Strict-JSON conversion of search results (no NaN or inf in the output)."""
import dataclasses
import math
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel


def to_json(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return to_json(obj.model_dump(mode="json"))
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, np.ndarray):
        return to_json(obj.tolist())
    if isinstance(obj, np.generic):
        return to_json(obj.item())
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


def electrical_deg_from_unaligned(theta_mech: float, n_rotor_poles: int) -> float:
    """Electrical degrees from the unaligned position; the engine's θ = 0 is phase A aligned."""
    return math.degrees((theta_mech - math.pi / n_rotor_poles) * n_rotor_poles)


def evaluation_json(ev) -> dict:
    out = to_json(ev)
    if ev.envelope is not None:
        nr = ev.design.machine.n_rotor_poles
        env = out["envelope"]
        for name in ("on", "off"):
            theta = getattr(ev.envelope, f"theta_{name}")
            env[f"theta_{name}_el"] = to_json([electrical_deg_from_unaligned(t, nr) for t in theta])
        env["efficiency"] = to_json(ev.envelope.efficiency)
    return out


def search_result_json(r) -> dict:
    return {
        "requirements": to_json(r.requirements),
        "sampled": r.sampled,
        "dropped": to_json(r.dropped),
        "stage1_rejected": r.stage1_rejected,
        "cancelled": r.cancelled,
        "evaluations": [evaluation_json(e) for e in r.evaluations],
        "pareto_ids": [e.id for e in r.pareto()],
    }
