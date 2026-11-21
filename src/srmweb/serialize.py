"""Strict-JSON conversion of search results (no NaN or inf in the output)."""
import dataclasses
import math
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from srmapp.thermal_summary import summary as thermal_summary


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


def _speed_detail(s) -> dict:
    return {"envelope_nm": s.envelope_nm, "continuous_nm": s.continuous_nm, "peak_nm": s.peak_nm,
            "hot_spot_c": s.continuous_hot_spot.temperature_c, "hot_spot_at": s.continuous_hot_spot.location,
            "peak_hot_spot_c": s.peak_hot_spot.temperature_c, "peak_hot_spot_at": s.peak_hot_spot.location,
            "rotor_c": s.rotor_c, "rotor_peak_c": s.rotor_peak_c, "bore_c": s.bore_c, "bore_peak_c": s.bore_peak_c,
            "start_nm": s.start_nm, "note": s.note}


def _cooling(c) -> dict:
    kind = " + ".join(n.replace("_", " ") for n in ("jacket", "end_spray", "shaft_oil", "slot_oil")
                      if getattr(c, n) is not None)
    return {"kind": kind or "none", "placeholder": c.placeholder, "ambient_c": c.ambient_c,
            "housing_thickness": c.housing_thickness, "jacket": c.jacket, "end_spray": c.end_spray,
            "shaft_oil": c.shaft_oil, "slot_oil": c.slot_oil}


def rating_json(r, air_gap_m: float | None = None) -> dict:
    """The whole rating. The flat per-speed keys and the stress status are the R5c summary, kept for older readers."""
    speeds = [{"rpm": n.rpm, "nominal_continuous_nm": n.continuous_nm, "nominal_peak_nm": n.peak_nm,
               "rated_continuous_nm": q.continuous_nm, "rated_peak_nm": q.peak_nm,
               "hot_spot_c": q.continuous_hot_spot.temperature_c, "hot_spot_at": q.continuous_hot_spot.location,
               "peak_hot_spot_c": q.peak_hot_spot.temperature_c, "peak_hot_spot_at": q.peak_hot_spot.location,
               "nominal": _speed_detail(n), "rated": _speed_detail(q)}
              for n, q in zip(r.nominal, r.rated)]
    st = r.stress
    return to_json({
        "speeds": speeds, "limit_c": r.limit_c, "insulation_class": r.insulation_class,
        "stress_status": st.status, "stress_safety_factor": st.safety_factor, "notes": list(r.notes),
        "shares": [{"row": s.row, "rpm": s.rpm, "hot_spot_rise_k": s.hot_spot_rise_k} for s in r.shares],
        "gap": {"cases": {k: dataclasses.asdict(v) for k, v in r.gap.items()}, "air_gap_m": air_gap_m},
        "stress": {"status": st.status, "safety_factor": st.safety_factor, "governing": st.governing,
                   "speed_limit_rpm": st.speed_limit_rpm, "check_speed_rpm": st.check_speed_rpm, "note": st.note},
        "torque_factor": r.torque_factor, "cooling": _cooling(r.cooling), "srmapp_version": r.srmapp_version})


def evaluation_json(ev, *, waveforms: bool = True, fields_key: str | None = None, requirements=None) -> dict:
    """`requirements` adds the plain-word thermal summary; `fields_key` names the temperature-field file."""
    out = to_json(dataclasses.replace(ev, rating=None))
    out["rating"] = (None if ev.rating is None else
                     rating_json(ev.rating, ev.design.machine.air_gap))
    out["thermal_fields"] = fields_key
    out["thermal_summary"] = (None if requirements is None
                              else to_json(thermal_summary(ev.rating, ev.thermal_check, requirements)))
    if ev.envelope is not None:
        nr = ev.design.machine.n_rotor_poles
        env = out["envelope"]
        for name in ("on", "off"):
            theta = getattr(ev.envelope, f"theta_{name}")
            env[f"theta_{name}_el"] = to_json([electrical_deg_from_unaligned(t, nr) for t in theta])
        env["efficiency"] = to_json(ev.envelope.efficiency)
        wf = ev.envelope.waveforms
        if not waveforms:
            env.pop("waveforms", None)
        elif wf is not None:
            env["waveforms"]["theta_el"] = to_json([electrical_deg_from_unaligned(t, nr) for t in wf.theta])
    return out


def search_result_json(r, fields_keys: dict[str, str] | None = None) -> dict:
    return {
        "requirements": to_json(r.requirements),
        "sampled": r.sampled,
        "dropped": to_json(r.dropped),
        "stage1_rejected": r.stage1_rejected,
        "cancelled": r.cancelled,
        "evaluations": [evaluation_json(e, waveforms=False, fields_key=(fields_keys or {}).get(e.id),
                                        requirements=r.requirements) for e in r.evaluations],
        "pareto_ids": [e.id for e in r.pareto()],
    }
