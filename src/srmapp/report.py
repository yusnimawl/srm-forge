"""Rule-based findings for the run report. Inputs are the stored JSON dicts of a case's results; a missing, None
or non-finite input gives no finding."""
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from srmapp.case import CaseInputs
from srmapp.drive.envelope import line_current

Level = Literal["warn", "note", "ok", "missing"]

IRON_UNCERTAINTY_WARN = 0.30   # relative iron-loss uncertainty above which the iron loss is flagged


@dataclass(frozen=True)
class Finding:
    id: str
    level: Level
    topic: str
    text: str
    value: float | None = None
    unit: str = ""


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _pct(frac: float) -> str:
    p = 100 * frac
    return f"{p:.1f} %" if abs(p) < 10 else f"{p:.0f} %"


def torque_ripple(torque: np.ndarray, n_phases: int) -> float | None:
    """(max - min) / mean of the sum of the phase torques; `torque` is phase A over one rotor pole pitch."""
    total = line_current(np.asarray(torque, dtype=float), n_phases)
    if not np.all(np.isfinite(total)) or not total.mean() > 0:
        return None
    return float((total.max() - total.min()) / total.mean())


def _version(v) -> tuple[int, ...] | None:
    try:
        parts = tuple(int(p) for p in str(v).split("."))
    except ValueError:
        return None
    return parts if len(parts) == 3 else None


def _ratio(out, id_, name, ratio, margin):
    if (r := _num(ratio)) is None:
        return
    out.append(Finding(id_, "warn" if r < margin else "ok", "requirements",
                       f"{name} ×{r:.2f} (margin ×{margin:.2f})", r))


def _evaluation(out, inputs, e):
    req, machine = inputs.requirements, inputs.design.machine
    if isinstance(e.get("feasible"), bool):
        out.append(Finding("feasible", "ok" if e["feasible"] else "warn", "requirements",
                           "Meets the requirements" if e["feasible"] else "Does not meet the requirements"))
    margin = inputs.search_settings().resolved_margin
    _ratio(out, "torque_ratio", "Torque", e.get("torque_ratio"), margin)
    _ratio(out, "power_ratio", "Power", e.get("power_ratio"), margin)
    j, lim = _num(e.get("j_rms")), _num(e.get("j_limit"))
    if j is not None and lim is not None:
        out.append(Finding("j_rms", "warn" if j > lim else "ok", "current density",
                           f"Conductor RMS current density {j / 1e6:.2f} A/mm² (limit {lim / 1e6:.2f} A/mm²)",
                           j / 1e6, "A/mm²"))
    mass = _num(e.get("mass_kg"))
    if mass is not None and req.max_mass_kg:
        f = mass / req.max_mass_kg
        out.append(Finding("mass", "warn" if f > 1 else "note", "mass",
                           f"Active mass {mass:.2f} kg is {_pct(f)} of the {req.max_mass_kg:g} kg limit", 100 * f, "%"))
    if req.max_outer_diameter_m:
        f = 2 * machine.stator_outer_radius / req.max_outer_diameter_m
        out.append(Finding("outer_diameter", "note", "size",
                           f"Outer diameter is {_pct(f)} of the {1000 * req.max_outer_diameter_m:.0f} mm limit",
                           100 * f, "%"))
    curves = e.get("curves") or {}
    la_sat = curves.get("la_sat") or []
    unsat = _num(curves.get("la_unsat"))
    last = _num(la_sat[-1]) if la_sat else None
    if last is not None and unsat:
        f = last / unsat
        out.append(Finding("saturation", "note", "saturation",
                           f"La at I_max is {_pct(f)} of unsaturated La", 100 * f, "%"))
    if (r := _num((e.get("key") or {}).get("la_lu"))) is not None:
        out.append(Finding("la_lu", "note", "saturation", f"La/Lu is {r:.2f}", r))
    env = e.get("envelope") or {}
    torque = (env.get("waveforms") or {}).get("torque")
    speeds = env.get("speeds_rpm")
    if torque is not None and speeds:
        s = np.array([np.nan if v is None else v for v in speeds], dtype=float)
        if np.isfinite(s).any():
            base = int(np.nanargmin(np.abs(s - req.base_speed_rpm)))
            row = np.array([np.nan if v is None else v for v in torque[base]], dtype=float)
            if (r := torque_ripple(row, machine.n_phases)) is not None:
                out.append(Finding("ripple", "note", "ripple",
                                   f"Torque ripple at base speed is {_pct(r)} (peak to peak over mean)", 100 * r, "%"))
    if (eff := _num(e.get("efficiency_base"))) is not None:
        out.append(Finding("efficiency_base", "note", "efficiency",
                           f"Efficiency at base speed is {_pct(eff)}", 100 * eff, "%"))


def _losses(out, l):
    pts, nt = l.get("points") or [], len(l.get("torque_fractions") or [])
    if not pts or not nt:
        return
    rated = max((i for i in range(len(pts) // nt) if pts[i * nt + nt - 1].get("reached")), default=None)
    if rated is not None:
        p = pts[rated * nt + nt - 1]
        cdc, cac = _num(p.get("copper_dc_w")), _num(p.get("copper_ac_w")) or 0.0
        iron = _num(p.get("iron_w"))
        terms = {(r, t): _num(w) for r, d in (p.get("iron") or {}).items() for t, w in d.items()}
        terms = {k: w for k, w in terms.items() if w is not None}
        if iron is None and terms:
            iron = sum(terms.values())
        rpm = f" ({r:.0f} rpm)" if (r := _num(p.get("speed_rpm"))) is not None else ""
        if cdc is not None and iron is not None and cdc + cac + iron > 0:
            tot = cdc + cac + iron
            out.append(Finding("loss_split", "note", "losses",
                               f"At the rated point{rpm} copper DC {_pct(cdc / tot)}, "
                               f"copper AC {_pct(cac / tot)}, iron {_pct(iron / tot)} of the loss",
                               100 * iron / tot, "%"))
        if terms:
            (region, term), w = max(terms.items(), key=lambda kv: kv[1])
            out.append(Finding("iron_region", "note", "losses",
                               f"Largest iron loss at the rated point: {region}, {term}, {w:.1f} W", w, "W"))
    unreached = sum(1 for p in pts if not p.get("reached"))
    out.append(Finding("losses_unreached", "warn" if unreached else "ok", "losses",
                       f"{unreached} operating points not reached" if unreached else "All operating points reached",
                       unreached))
    beyond = sum(1 for p in pts if p.get("beyond_fit_range"))
    out.append(Finding("beyond_fit", "warn" if beyond else "ok", "losses",
                       f"{beyond} points beyond the iron-loss fit range" if beyond else
                       "All points inside the iron-loss fit range", beyond))
    unc = [u for p in pts if (u := _num(p.get("iron_uncertainty_rel"))) is not None]
    if unc:
        m = max(unc)
        out.append(Finding("iron_uncertainty", "warn" if m > IRON_UNCERTAINTY_WARN else "note", "losses",
                           f"Iron-loss uncertainty up to {_pct(m)}", 100 * m, "%"))


def _validation(out, v):
    checks = v.get("checks") or []
    bad = [c for c in checks if c.get("status") in ("fail", "warn")]
    for c in bad:
        out.append(Finding(f"check:{c['name']}", "warn", "validation",
                           f"{c['name']} {c['status']}" + "".join(
                               f", {k} {x:.4g}" for k in ("value", "limit") if (x := _num(c.get(k))) is not None)
                           + f"; {c.get('detail', '')}", _num(c.get("value"))))
    if checks and not bad:
        out.append(Finding("checks", "ok", "validation", f"All {len(checks)} checks pass", len(checks)))
    if v.get("label") is None:
        out.append(Finding("label", "warn", "validation", "The case does not carry the 2D-verified label"))
    budget = v.get("budget") or {}
    for q in budget.get("total") or {}:
        rows = [(r["rel"][q], r["source"]) for r in budget.get("rows") or []
                if _num((r.get("rel") or {}).get(q)) is not None]
        if rows:
            rel, src = max(rows)
            out.append(Finding(f"budget:{q}", "note", "budget",
                               f"Largest uncertainty in {q}: {src}, {_pct(rel)}", 100 * rel, "%"))


def _dxf(out, rows):
    ch = [(abs(r["after"] / r["before"] - 1), r) for r in rows
          if _num(r.get("before")) and _num(r.get("after")) is not None]
    for d, r in sorted(ch, key=lambda t: -t[0])[:3]:
        out.append(Finding("dxf", "note", "dxf",
                           f"{r['name']} changed {_pct(d)}: {r['before']:.4g} to {r['after']:.4g} {r['unit']}".rstrip(),
                           100 * d, "%"))


def findings(inputs: CaseInputs, evaluation: Mapping, validation: Mapping | None, losses: Mapping | None,
             compare: Sequence[Mapping] | None, animation_missing: str | None) -> list[Finding]:
    out: list[Finding] = []
    _evaluation(out, inputs, evaluation)
    if losses is not None:
        _losses(out, losses)
    if validation is not None:
        _validation(out, validation)
    if compare:
        _dxf(out, compare)
    if losses is None:
        out.append(Finding("losses_missing", "missing", "data", "Losses not run"))
    if validation is None:
        out.append(Finding("validation_missing", "missing", "data", "Validation not run"))
    if animation_missing is not None:
        out.append(Finding("animation_missing", "missing", "data", f"Animation unavailable: {animation_missing}"))
    if losses is not None:
        lv, ev = _version(losses.get("srmapp_version")), _version(evaluation.get("srmapp_version"))
        if lv and ev and lv < ev:
            out.append(Finding("losses_stale", "missing", "data",
                               f"Losses were computed with srmapp {losses['srmapp_version']}, "
                               f"the evaluation with {evaluation['srmapp_version']}"))
    return out
