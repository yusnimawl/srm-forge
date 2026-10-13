"""README comparison: the summary table, per-machine details and SVG charts built from the result files."""

from __future__ import annotations

import io
import os
import posixpath
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import rc_context  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from . import BENCH_DIR, BENCH_VERSION  # noqa: E402
from .result import Result, read_results  # noqa: E402

START = "<!-- srmbench:results:start -->"
END = "<!-- srmbench:results:end -->"

REFERENCE_FILE = BENCH_DIR / "reference-machine.txt"

GREY = "#8a8a8a"
AMBER = "#e8b04a"
HATCH_COLOR = "#555555"
LINE_COLORS = ["#e8b04a", "#9bd88a", "#e07fb5", "#f2716b", "#c3a6f0"]
LINE_DASHES = ["dashed", "dotted", "dashdot", (0, (8, 3)), (0, (8, 3, 2, 3))]

_RC = {
    "svg.hashsalt": "srmbench",
    "svg.fonttype": "path",
    "text.color": GREY,
    "axes.labelcolor": GREY,
    "axes.edgecolor": GREY,
    "axes.titlecolor": GREY,
    "xtick.color": GREY,
    "ytick.color": GREY,
    "grid.color": GREY,
    "legend.labelcolor": GREY,
    "figure.facecolor": "none",
    "axes.facecolor": "none",
    "savefig.facecolor": "none",
    "savefig.edgecolor": "none",
    "hatch.linewidth": 1.0,
}


def _start(r: Result) -> float:
    return datetime.fromisoformat(r.started).timestamp()


def latest_per_machine(results: list[Result]) -> list[Result]:
    """The newest complete result of each label at the current bench version, fastest full map first."""
    newest: dict[str, Result] = {}
    for r in results:
        if r.bench_version != BENCH_VERSION or "full_map_s" not in r.summary:
            continue
        if r.label not in newest or _start(r) >= _start(newest[r.label]):
            newest[r.label] = r
    return sorted(newest.values(), key=lambda r: (r.summary["full_map_s"]["value"], r.label))


def _index(row: Result, ref: Result | None) -> tuple[int, int] | None:
    """(single-core, all-core) index of `row` against `ref`, the reference being 100."""
    if ref is None:
        return None
    single = ref.summary["single_solve_s"] / row.summary["single_solve_s"] * 100
    everything = row.summary["throughput_per_min"] / ref.summary["throughput_per_min"] * 100
    return round(single), round(everything)


def _reference(rows: list[Result], reference_label: str | None) -> Result | None:
    return next((r for r in rows if r.label == reference_label), None)


# ---- charts -------------------------------------------------------------------------------------------------

def _svg(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", transparent=True, metadata={"Date": None})
    return buf.getvalue()


def _style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)


def _bar(ax, y: float, value: float, height: float, color: str, hatch: str | None):
    return ax.barh(y, value, height=height, color=color, edgecolor=HATCH_COLOR, linewidth=0, hatch=hatch)


def full_map_chart(rows: list[Result], reference_label: str | None) -> bytes:
    with rc_context(_RC):
        fig = Figure(figsize=(8.0, 1.1 + 0.5 * len(rows)))
        ax = fig.subplots()
        top = max(r.summary["full_map_s"]["value"] for r in rows) / 60
        for i, r in enumerate(rows):
            m = r.summary["full_map_s"]
            minutes = m["value"] / 60
            projected = not m["measured"]
            _bar(ax, i, minutes, 0.62, GREY if r.label == reference_label else AMBER, "//" if projected else None)
            ax.text(minutes + top * 0.01, i, f"{'~' if projected else ''}{_minutes(m['value'])} min",
                    va="center", ha="left", fontsize=9)
        ax.set_yticks(range(len(rows)), [r.label for r in rows])
        ax.invert_yaxis()
        ax.set_xlim(0, top * 1.18)
        ax.set_xlabel("minutes for the full 8/6 map (lower is better; hatched = projected)")
        _style(ax)
        fig.tight_layout()
        return _svg(fig)


def _line_styles(rows: list[Result], reference_label: str | None) -> dict[str, tuple[str, object]]:
    """Colour and dash per label: the reference grey and solid, the others by label order."""
    styles: dict[str, tuple[str, object]] = {}
    others = sorted(r.label for r in rows if r.label != reference_label)
    for i, label in enumerate(others):
        styles[label] = (LINE_COLORS[i % len(LINE_COLORS)], LINE_DASHES[i % len(LINE_DASHES)])
    if reference_label is not None:
        styles[reference_label] = (GREY, "solid")
    return styles


def scaling_chart(rows: list[Result], reference_label: str | None) -> bytes | None:
    """Solves per minute against workers; None when no machine has two batches."""
    drawn = [r for r in rows if len(r.steps.get("batches", [])) >= 2]
    if not drawn:
        return None
    styles = _line_styles(rows, reference_label)
    with rc_context(_RC):
        fig = Figure(figsize=(8.0, 4.6))
        ax = fig.subplots()
        workers: set[int] = set()
        for r in sorted(drawn, key=lambda r: r.label):
            batches = sorted(r.steps["batches"], key=lambda b: b["workers"])
            color, dash = styles[r.label]
            ax.plot([b["workers"] for b in batches], [b["per_min"] for b in batches], color=color, linestyle=dash,
                    linewidth=2, marker="o", markersize=4, label=r.label)
            workers.update(b["workers"] for b in batches)
        ax.set_xticks(sorted(workers))
        ax.set_xlabel("workers")
        ax.set_ylabel("solves per minute")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(frameon=False, handlelength=3.6, loc="upper left")
        fig.tight_layout()
        return _svg(fig)


def index_chart(rows: list[Result], ref: Result) -> bytes:
    with rc_context(_RC):
        fig = Figure(figsize=(8.0, 1.3 + 0.7 * len(rows)))
        ax = fig.subplots()
        h = 0.36
        top = 100.0
        for i, r in enumerate(rows):
            single, everything = _index(r, ref)
            top = max(top, single, everything)
            _bar(ax, i - h / 2, single, h, GREY, None)
            _bar(ax, i + h / 2, everything, h, AMBER, "..")
            ax.text(single + top * 0.01, i - h / 2, str(single), va="center", ha="left", fontsize=8)
            ax.text(everything + top * 0.01, i + h / 2, str(everything), va="center", ha="left", fontsize=8)
        ax.axvline(100, color=GREY, linewidth=1, linestyle="dashed", alpha=0.6)
        ax.set_yticks(range(len(rows)), [r.label for r in rows])
        ax.invert_yaxis()
        ax.set_xlim(0, top * 1.15)
        ax.set_xlabel(f"index, {ref.label} = 100 (higher is faster)")
        ax.legend(handles=[Patch(facecolor=GREY, label="single core"),
                           Patch(facecolor=AMBER, edgecolor=HATCH_COLOR, linewidth=0, hatch="..", label="all cores")],
                  frameon=False, loc="lower right")
        _style(ax)
        fig.tight_layout()
        return _svg(fig)


# ---- markdown -----------------------------------------------------------------------------------------------

def _md(x) -> str:
    """Text for a table cell or inline use: no pipes, angle brackets or line breaks."""
    return (str(x).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\r", " ").replace("\n", " "))


def _num(x: float) -> str:
    return f"{x:.1f}" if abs(x) < 10 else f"{x:.0f}"


def _minutes(seconds: float) -> str:
    return _num(seconds / 60)


def _projected(value: dict, text: str) -> str:
    return text if value["measured"] else f"~{text}"


def _os(machine: dict) -> str:
    system = machine.get("os")
    if system == "Windows":
        try:
            build = int(str(machine.get("os_version", "")).split(".")[-1])
        except ValueError:
            return "Windows"
        return "Windows 11" if build >= 22000 else "Windows 10"
    if system == "Linux":
        return f"Linux (glibc {machine['glibc']})" if machine.get("glibc") else "Linux"
    return str(system or "unknown")


def _mark(correctness: dict) -> str:
    return {"pass": "✓", "fail": "✗"}.get(correctness["status"], "–")


def _or_dash(value, fmt) -> str:
    return "–" if value is None else fmt(value)


def _filenames(results: list[Result]) -> dict[int, str]:
    """File name of each result, as `result.write_result` names it: a repeat of a label, minute and tier gets
    -2, -3, ... in the order the runs finished."""
    groups: dict[tuple, list[Result]] = defaultdict(list)
    for r in results:
        stamp = datetime.fromisoformat(r.started).strftime("%Y-%m-%dT%H%M")
        groups[(r.label, stamp, r.tier)].append(r)
    names: dict[int, str] = {}
    for (_, stamp, tier), members in groups.items():
        for n, r in enumerate(sorted(members, key=lambda m: m.finished), start=1):
            names[id(r)] = f"{stamp}-{tier}.json" if n == 1 else f"{stamp}-{tier}-{n}.json"
    return names


def _summary_table(rows: list[Result], ref: Result | None) -> list[str]:
    head = ["Machine", "CPU", "Cores", "RAM (GB)", "OS", "Tier", "Single solve (s)", "Workers",
            "Screening map (min)", "Full map (min)", "Search of 24 (h)", "RAM per worker (GB)", "Throttle (%)",
            "Correct", "Index single/all"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        s, m = r.summary, r.machine
        idx = _index(r, ref)
        cells = [
            f"[{_md(r.label)}](#{_anchor(r.label)})",
            _md(m.get("cpu_model", "unknown")),
            f"{m.get('physical_cores') or '?'}C/{m.get('logical_cpus') or '?'}T",
            _num(m["ram_gb"]) if m.get("ram_gb") is not None else "–",
            _md(_os(m)),
            r.tier,
            _num(s["single_solve_s"]),
            str(s["recommended_workers"]),
            _projected(s["screening_map_s"], _minutes(s["screening_map_s"]["value"])),
            _projected(s["full_map_s"], _minutes(s["full_map_s"]["value"])),
            f"~{_num(s['search_h'])}",
            _or_dash(s["peak_ram_worker_gb"], lambda v: f"{v:.2f}"),
            _or_dash(s["throttle_pct"], lambda v: f"{v:+.1f}"),
            _mark(s["correctness"]),
            "" if idx is None else f"{idx[0]}/{idx[1]}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _anchor(label: str) -> str:
    return f"machine-{label}"


def _table(head: list[str], body: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    lines += ["| " + " | ".join(_md(c) for c in row) + " |" for row in body]
    return lines


def _by_preset(d: dict) -> list[tuple[str, dict]]:
    return sorted(d.items(), key=lambda kv: (kv[0] != "screening", kv[0]))


def _step_lines(r: Result) -> list[str]:
    st = r.steps
    out: list[str] = []

    def add(*lines: str) -> None:
        out.extend(lines)
        out.append("")

    add("**Mesh (8/6)**")
    add(*_table(["Preset", "Seconds", "Nodes", "Grid points"],
                [[k, f"{v['seconds']:.2f}", f"{v['nodes']:,}".replace(",", " "), str(v["points"])]
                 for k, v in _by_preset(st["mesh"])]))
    add("**Single solve (8/6)**")
    add(*_table(["Preset", "Median (s)", "Samples (s)"],
                [[k, f"{v['median']:.3f}", ", ".join(f"{x:.3f}" for x in v["samples"])]
                 for k, v in _by_preset(st["single_solve"])]))
    c = st["correctness_points"]["correctness"]
    add(f"**Correctness points:** {c['status']}" + "".join(f"; {_md(d)}" for d in c["details"]))
    add("**Batches**")
    add(*_table(["Workers", "Points", "Seconds", "Solves per minute", "Peak RAM per worker (GB)"],
                [[str(b["workers"]), str(b["points"]), f"{b['seconds']:.2f}", f"{b['per_min']:.1f}",
                  _or_dash(b.get("peak_ram_gb"), lambda v: f"{v:.2f}")] for b in st["batches"]]))
    if "recommended" in st:
        rec = st["recommended"]
        cap = "none" if rec["ram_cap"] is None else rec["ram_cap"]
        add(f"**Recommended workers:** {rec['workers']} (uncapped choice {rec['uncapped']}, RAM cap {cap})")
    if "screening_map" in st:
        m = st["screening_map"]
        keys = ", ".join(f"{k} {v:.6g}" for k, v in m["key_numbers"].items())
        add(f"**Screening map 8/6:** {m['seconds']:.1f} s, {m['points']} points, {m['workers']} workers, "
            f"correctness {m['correctness']['status']}" + "".join(f"; {_md(d)}" for d in m["correctness"]["details"])
            + f"; key numbers: {_md(keys)}")
    if "sustained" in st:
        sus = st["sustained"]
        trace = "; ".join(f"{b['t']:.0f} s: {b['per_min']:.1f}" for b in sus["batches"])
        add(f"**Sustained load:** {sus['minutes']} min at {sus['workers']} workers, throttle {sus['throttle_pct']:+.1f} %; "
            f"trace (time: solves per minute): {trace}")
    for name, entry in st.get("full_maps", {}).items():
        m = entry["map"]
        add(f"**Full map {name.replace('_', '/')}:** {m['seconds']:.1f} s, {m['points']} points, "
            f"{entry['workers']} workers; extras {entry['extras']['seconds']:.1f} s")
    return out


def _scaling_lines(r: Result) -> list[str]:
    batches = r.steps["batches"]
    base = min(batches, key=lambda b: b["workers"])
    rows = []
    for b in sorted(batches, key=lambda b: b["workers"]):
        speedup = b["per_min"] / base["per_min"]
        rows.append([str(b["workers"]), f"{b['per_min']:.1f}", f"{speedup:.2f}",
                     f"{speedup * base['workers'] / b['workers'] * 100:.0f}"])
    return _table(["Workers", "Solves per minute", f"Speed-up over {base['workers']} worker(s)", "Efficiency (%)"], rows)


def _run_row(r: Result, name: str) -> list[str]:
    s = r.summary
    full = s.get("full_map_s")
    return [r.started[:16].replace("T", " "), r.tier, r.bench_version, f"[{name}]", r.status,
            _num(s["single_solve_s"]) if "single_solve_s" in s else "–",
            "–" if full is None else _projected(full, _minutes(full["value"]))]


def _details(r: Result, history: list[Result], names: dict[int, str], link) -> list[str]:
    m, s = r.machine, r.summary
    cpu = _md(m.get("cpu_model", "unknown"))
    lines = [f'<details id="{_anchor(r.label)}">',
             f"<summary><b>{_md(r.label)}</b> – {cpu}, {r.tier}, {r.started[:10]}</summary>", ""]
    lines += [
        f"- Machine: {cpu}; {m.get('physical_cores') or '?'} cores, {m.get('logical_cpus') or '?'} threads; "
        f"{m.get('ram_gb')} GB RAM; {_md(_os(m))} ({_md(m.get('os_version', ''))}, {_md(m.get('arch', ''))}); "
        f"Python {_md(m.get('python', ''))}",
        "- Versions: " + ", ".join(f"{k} {v}" for k, v in r.versions.items() if v is not None)
        + f"; srmbench {r.bench_version}; lock {r.lock_hash}",
        f"- Run: {r.started} to {r.finished}, tier {r.tier}, status {r.status}",
        f"- Result file: [{names[id(r)]}]({link(r)})",
    ]
    if s.get("projection_error_pct"):
        e = s["projection_error_pct"]
        lines.append(f"- Projection error against the measured maps: screening {e['screening']:+.1f} %, "
                     f"full {e['full']:+.1f} %")
    lines += [f"- Warning: {_md(w)}" for w in r.warnings]
    lines.append("")
    lines += _step_lines(r)
    if len(r.steps["batches"]) >= 2:
        lines += ["**Scaling**", ""] + _scaling_lines(r) + [""]
    if len(history) > 1:
        lines += ["**All runs of this machine**", ""]
        lines += _table(["Started", "Tier", "Version", "File", "Status", "Single solve (s)", "Full map (min)"],
                        [_run_row(h, names[id(h)]) for h in history])
        lines.append("")
        lines.append("Files: " + ", ".join(f"[{names[id(h)]}]({link(h)})" for h in history))
        lines.append("")
    lines += ["</details>", ""]
    return lines


def render_block(results: list[Result], reference_label: str | None, charts_rel: str) -> str:
    """The markdown between the README markers: charts, summary table, details per machine, older versions."""
    rows = latest_per_machine(results)
    if not rows:
        return "_No results yet._"
    ref = _reference(rows, reference_label)
    names = _filenames(results)
    results_rel = posixpath.dirname(charts_rel)

    def link(r: Result) -> str:
        return posixpath.join(results_rel, r.label, names[id(r)])

    lines: list[str] = [f"![Full 8/6 map time]({charts_rel}/full_map.svg)", ""]
    if any(len(r.steps.get("batches", [])) >= 2 for r in rows):
        lines += [f"![Solves per minute against workers]({charts_rel}/scaling.svg)", ""]
    if ref is not None:
        lines += [f"![Single-core and all-core index]({charts_rel}/index.svg)", ""]
    lines += _summary_table(rows, ref)
    lines += ["", "`~` marks a projected value (a map not run, estimated from the batch throughput); the search is "
              "always projected. Correct: ✓ passed, ✗ failed, – not checked."]
    lines.append("")
    for r in rows:
        history = sorted((h for h in results if h.label == r.label and h.bench_version == BENCH_VERSION),
                         key=lambda h: _start(h), reverse=True)
        lines += _details(r, history, names, link)
    older = [r for r in results if r.bench_version != BENCH_VERSION]
    if older:
        lines += ["### Older benchmark versions", "",
                  "Left out of the charts and the table, because their numbers are not comparable.", ""]
        for r in sorted(older, key=lambda r: (r.label, _start(r))):
            lines.append(f"- {_md(r.label)}: [{names[id(r)]}]({link(r)}) (srmbench {_md(r.bench_version)})")
        lines.append("")
    return "\n".join(lines).rstrip("\n")


# ---- build --------------------------------------------------------------------------------------------------

def _reference_label() -> str | None:
    try:
        return REFERENCE_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_chart(path: Path, data: bytes | None) -> None:
    if data is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(data)


def build_report(results_dir: Path, readme: Path, reference_label: str | None) -> None:
    """Write the charts under `results_dir/charts` and replace the block between the README markers.
    `reference_label` None means the label in `bench/reference-machine.txt`."""
    results_dir, readme = Path(results_dir), Path(readme)
    with open(readme, encoding="utf-8", newline="") as f:
        text = f.read()
    start, end = text.find(START), text.find(END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"{readme} must contain {START} followed by {END}.")
    if reference_label is None:
        reference_label = _reference_label()

    results = read_results(results_dir)
    rows = latest_per_machine(results)
    ref = _reference(rows, reference_label)
    charts = results_dir / "charts"
    if rows:
        charts.mkdir(parents=True, exist_ok=True)
    if charts.is_dir():
        _write_chart(charts / "full_map.svg", full_map_chart(rows, reference_label) if rows else None)
        _write_chart(charts / "scaling.svg", scaling_chart(rows, reference_label) if rows else None)
        _write_chart(charts / "index.svg", index_chart(rows, ref) if ref is not None else None)

    charts_rel = Path(os.path.relpath(charts, readme.parent)).as_posix()
    block = render_block(results, reference_label, charts_rel)
    newline = "\r\n" if "\r\n" in text else "\n"
    block = block.replace("\n", newline)
    new = text[:start] + START + newline + block + newline + text[end:]
    if new != text:
        with open(readme, "w", encoding="utf-8", newline="") as f:
            f.write(new)
