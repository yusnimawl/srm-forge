r"""Validation report (spec §8.6): reads the committed result JSON and writes docs/validation-report.md and its
plots. Regenerate on every version bump before tagging.

Usage: python tools\validation_report.py      (exit code 1 when the verdict is FAIL)
"""
import json
import sys
from importlib.metadata import PackageNotFoundError, metadata, version
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from srmcore.maps.fem_checks import BAND_RADIUS_TOLERANCE, PSI_TOLERANCE, TORQUE_TOLERANCE  # noqa: E402
from srmcore.materials.library import available_materials, load_material  # noqa: E402
from srmcore.materials.schema import SoftMagneticMaterial  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ("numpy", "scipy", "gmsh", "scikit-fem", "ngsolve", "netgen-mesher", "h5py", "pydantic", "matplotlib")
STATUS_CELL = {"pass": "pass", "fail": "**FAIL**", "missing": "**missing**", "pending": "pending"}
NOT_RUN = "not run (input file missing)\n"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _save_plot(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _num(x, scale: float = 1, fmt: str = "g") -> str:
    """A number cell; the producer writes null for non-finite values."""
    return "—" if x is None else format(scale * x, fmt)


def _pct(x: float) -> str:
    return f"{100 * x:.2f} %"


def engine_section():
    rows = []
    for dist in ("srmcore", *DEPENDENCIES):
        try:
            md = metadata(dist)
            lic = md.get("License-Expression") or md.get("License") or "see package"
            rows.append(f"| {dist} | {version(dist)} | {lic.splitlines()[0][:60]} |")
        except PackageNotFoundError:
            rows.append(f"| {dist} | not installed | |")
    return "## Engine\n\n| Package | Version | Licence |\n|---|---|---|\n" + "\n".join(rows) + "\n", []


def material_section():
    rows = []
    for name in available_materials():
        m = load_material(name)
        if not isinstance(m, SoftMagneticMaterial):
            continue
        dig = "—" if m.digitisation_error is None else _pct(m.digitisation_error)
        prov = ", ".join(m.provisional_fields) or "—"
        rows.append(f"| {name} | {m.confidence} | {m.saturation_polarisation:g} T | {m.stacking_factor:g} | {dig} | "
                    f"{prov} | {m.provenance.source[:80].replace('|', '/')} |")
    head = "| Material | Grade | Js | Stacking | Digitisation error | Provisional | Source |\n|---|---|---|---|---|---|---|\n"
    return "## Material library\n\n" + head + "\n".join(rows) + "\n", []


def m5a_section(m5a_dir: Path):
    path = m5a_dir / "heldout.jsonl"
    rows = []
    if path.is_file():
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rows = [r for r in map(json.loads, lines) if r["n_samples"] == 64]
    if not rows:
        return "## M5a mesh convergence\n\nheld-out limits: **missing** (no 64-sample rows)\n", ["missing"]
    out = [f"Limits: psi {_pct(PSI_TOLERANCE)}, torque {_pct(TORQUE_TOLERANCE)}, band radius {_pct(BAND_RADIUS_TOLERANCE)}.\n",
           "| Design | psi | torque | band radius | Status |\n|---|---|---|---|---|"]
    statuses = []
    for r in rows:
        ok = (r["held_out_psi"] <= PSI_TOLERANCE and r["held_out_torque"] <= TORQUE_TOLERANCE
              and r["band_radius"] <= BAND_RADIUS_TOLERANCE)
        s = "pass" if ok else "fail"
        statuses.append(s)
        out.append(f"| {r['design']} | {_pct(r['held_out_psi'])} | {_pct(r['held_out_torque'])} | "
                   f"{_pct(r['band_radius'])} | {STATUS_CELL[s]} |")
    return "## M5a mesh convergence\n\n" + "\n".join(out) + "\n", statuses


def team24_section(data):
    head = "## M5b TEAM 24\n\nReport only (not gated).\n\n"
    if data is None:
        return head + NOT_RUN, []
    rows = ["| Quantity | Model | Measured | Error |\n|---|---|---|---|"]
    for key in ("static_torque", "rotor_flux"):
        d = data[key]
        rows.append(f"| {key} | {d['model']:g} | {d['measured']:g} | {d['error_pct']:+.1f} % |")
    c = data["current_rise_max_dev_pct"]
    rows.append(f"| current rise, max deviation | before {c['before']:g} % | after {c['after']:g} % | |")
    return head + "\n".join(rows) + "\n", []


def krishnan_section(data, plot_dir: Path):
    head = "## M5d Krishnan 6/4\n\nReport only (not gated).\n\n"
    if data is None:
        return head + NOT_RUN, []
    rows = ["| Quantity | Current | Measured | 2D model | With end winding | Error 2D | Error corrected | "
            "Uncertainty |\n|---|---|---|---|---|---|---|---|"]
    labels = []
    for r in data["rows"]:
        labels.append(f"{r['quantity']} {r['current']:g} A")
        rows.append(f"| {r['quantity']} ({r['unit']}) | {r['current']:g} A | {r['measured']:g} | {r['model_2d']:g} | "
                    f"{r['model_after']:g} | {r['error_before_pct']:+.1f} % | {r['error_after_pct']:+.1f} % | "
                    f"{r['unc_after_pct']:.1f} % |")
    fig, ax = plt.subplots(figsize=(7, 3.5))
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], [r["error_before_pct"] for r in data["rows"]], 0.4, label="2D")
    ax.bar([i + 0.2 for i in x], [r["error_after_pct"] for r in data["rows"]], 0.4, label="with end winding")
    ax.set_xticks(list(x), labels, rotation=45, ha="right")
    ax.set_ylabel("error against measurement (%)")
    ax.legend()
    _save_plot(fig, plot_dir / "krishnan.png")
    return head + "\n".join(rows) + "\n\n![krishnan](validation/krishnan.png)\n", []


def femm_section(data, plot_dir: Path):
    head = "## M5c FEMM\n\nGate: ratio of the worst error to its limit is at most 1.\n\n"
    if data is None:
        return head + "**missing**\n", ["missing"]
    rows = ["| Machine | worst psi | worst torque (rel) | worst torque (of peak) | Ratio | Status |\n|---|---|---|---|---|---|"]
    statuses = []
    for name, d in data.items():
        s = "pass" if d["ratio"] <= 1 else "fail"
        statuses.append(s)
        rows.append(f"| {name} | {_pct(d['worst_psi'])} | {_pct(d['worst_t_rel'])} | {_pct(d['worst_t_peak'])} | "
                    f"{d['ratio']:.3f} | {STATUS_CELL[s]} |")
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.bar(list(data), [d["ratio"] for d in data.values()])
    ax.axhline(1.0, color="k", linestyle="--")
    ax.set_ylabel("worst error / limit")
    _save_plot(fig, plot_dir / "femm.png")
    return head + "\n".join(rows) + "\n\n![femm](validation/femm.png)\n", statuses


def em_section(data, plot_dir: Path):
    head = "## EM validation (8/6 full)\n\n"
    if data is None:
        return head + "**missing**\n", ["missing"]
    out = [f"Engine {data['engine_version']}, label: {data['label'] or 'none'}, grades {data['material_grades']}, "
           f"map {data['map_s']:.0f} s, validation {data['validate_s']:.0f} s.\n",
           "| Check | Status | Value | Limit | Detail |\n|---|---|---|---|---|"]
    statuses = []
    for c in data["checks"]:
        if c["name"] != "engine_version":
            statuses.append(c["status"] if c["status"] == "pass" else "fail")
        out.append(f"| {c['name']} | {c['status']} | {_num(c['value'])} | {_num(c['limit'])} | {c['detail']} |")
    b = data["budget"]
    keys = b["keys"]
    out += ["", "Uncertainty budget (worst case, % of the corrected value):\n",
            "| Source | " + " | ".join(keys) + " |\n|---|" + "---|" * len(keys)]
    out.append("| 2D value | " + " | ".join(_num(b["values_2d"][k]) for k in keys) + " |")
    out.append("| corrected value | " + " | ".join(_num(b["values"][k]) for k in keys) + " |")
    for r in b["rows"]:
        out.append(f"| {r['source']} | " + " | ".join(_num(r["rel"][k], 100, ".2f") for k in keys) + " |")
    out.append("| **total** | " + " | ".join(f"**{_num(b['total'][k], 100, '.2f')}**" for k in keys) + " |")
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.bar(keys, [float("nan") if b["total"][k] is None else 100 * b["total"][k] for k in keys])
    ax.set_ylabel("total uncertainty (%)")
    _save_plot(fig, plot_dir / "budget.png")
    return head + "\n".join(out) + "\n\n![budget](validation/budget.png)\n", statuses


def speed_section(data, budgets):
    head = "## Speed\n\n"
    if data is None or budgets is None:
        return head + "**missing**\n", ["missing"]
    out = [f"srmcore {data['srmcore']}, {data['cpu']}, {data['logical_cpus']} logical CPUs, {data['workers']} workers, "
           f"{data['date']}.\n", "| Design | Item | Seconds | Budget | Status |\n|---|---|---|---|---|"]
    statuses = []
    for r in data["runs"]:
        budget = budgets.get(r["item"])
        s = "missing" if budget is None else ("pass" if r["seconds"] <= budget else "fail")
        statuses.append(s)
        out.append(f"| {r['design']} | {r['item']} | {r['seconds']:.1f} | {budget if budget is not None else 'unset'} | "
                   f"{STATUS_CELL[s]} |")
    return head + "\n".join(out) + "\n", statuses


def ci_section(data):
    head = "## CI\n\n"
    if data is None:
        return head + "**missing**\n", ["missing"]
    s = {"success": "pass", "failure": "fail", "pending": "pending"}.get(data["result"], "fail")
    return head + f"Tag {data['tag']}, run {data['run_url']}, result {data['result']}: {STATUS_CELL[s]}\n", [s]


def generate(data_dir: Path, m5a_dir: Path, out_md: Path) -> str:
    plot_dir = out_md.parent / "validation"
    sections = [
        ("Engine", engine_section()),
        ("Material library", material_section()),
        ("M5a mesh convergence", m5a_section(m5a_dir)),
        ("M5b TEAM 24", team24_section(_load(data_dir / "team24.json"))),
        ("M5c FEMM", femm_section(_load(data_dir / "femm.json"), plot_dir)),
        ("M5d Krishnan 6/4", krishnan_section(_load(data_dir / "krishnan_6_4.json"), plot_dir)),
        ("EM validation (8/6 full)", em_section(_load(data_dir / "em_validate_8_6.json"), plot_dir)),
        ("Speed", speed_section(_load(data_dir / "speed.json"), _load(data_dir / "speed_budgets.json"))),
        ("CI", ci_section(_load(data_dir / "ci.json"))),
    ]
    statuses = [s for _, (_, ss) in sections for s in ss]
    verdict = ("FAIL" if "fail" in statuses or "missing" in statuses
               else "PENDING" if "pending" in statuses else "PASS")
    flagged = [f"- {name}: {'/'.join(sorted(set(ss) - {'pass'}))}" for name, (_, ss) in sections if set(ss) - {"pass"}]
    text = f"# srmcore validation report\n\n**Verdict: {verdict}**\n\n" + "\n".join(flagged) + "\n\n"
    text += "\n".join(md for _, (md, _) in sections)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(text, encoding="utf-8")
    return verdict


if __name__ == "__main__":
    verdict = generate(ROOT / "docs" / "validation", ROOT / "docs" / "m5a-data", ROOT / "docs" / "validation-report.md")
    print(verdict)
    sys.exit(1 if verdict == "FAIL" else 0)
