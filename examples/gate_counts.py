"""Count what each gate of the search rejects for the bike requirement (no maps are built).

Usage: python examples/gate_counts.py [--ratios 8 12 15] [--n 250] [--json PATH]

Per ratio, `n` screening candidates (seed 0) go through the pole-set frequency limit, stage 1 and the hard limits the
way `srmapp.pipeline.run_search` does. Prints a markdown table per ratio: per pole set the candidates sampled, the
stage-1 passes and the limit rejections per limit (a design counts once under each limit it fails; the last column
counts designs that pass stage 1 and fail at least one limit)."""
import argparse
import json
from pathlib import Path

from bound_share import bike
from srmapp.limits import SEARCH_REQUIRES_PASS, frequency_limit, hard_limits
from srmapp.pipeline import SearchSettings
from srmapp.sizing.generator import sample_candidates
from srmapp.sizing.stage1 import stage1


def count(ratio: float, n: int) -> dict:
    req, settings = bike(ratio), SearchSettings(preset="screening")
    dropped, pole_sets = {}, []
    for ns, nr, m in settings.pole_sets:
        lim = frequency_limit(nr, req)
        if lim.status == "fail":
            dropped[f"{ns}/{nr}"] = lim.note
        else:
            pole_sets.append((ns, nr, m))
    cands, _ = sample_candidates(req, n, seed=settings.seed, pole_sets=pole_sets, materials=settings.materials,
                                 preset="screening")
    margin = settings.resolved_margin
    sets: dict[str, dict] = {}
    for c in cands:
        m = c.design.machine
        row = sets.setdefault(f"{m.n_stator_poles}/{m.n_rotor_poles}",
                              dict(sampled=0, stage1_pass=0, limit_rejected=0, by_limit={}))
        row["sampled"] += 1
        if not stage1(req, m, margin, settings.j_peak, settings.peak_cap).passes:
            continue
        row["stage1_pass"] += 1
        bad = [lim.name for lim in hard_limits(req, m)
               if lim.status == "fail" or (lim.status == "not_run" and lim.name in SEARCH_REQUIRES_PASS)]
        row["limit_rejected"] += bool(bad)
        for name in bad:
            row["by_limit"][name] = row["by_limit"].get(name, 0) + 1
    return dict(ratio=ratio, n=n, dropped_pole_sets=dropped, pole_sets=sets)


def table(r: dict) -> str:
    names = sorted({k for s in r["pole_sets"].values() for k in s["by_limit"]})
    lines = [f"Ratio {r['ratio']:g}. Dropped pole sets: "
             + ("; ".join(f"{k} ({v})" for k, v in r["dropped_pole_sets"].items()) or "none") + ".", "",
             "| Pole set | Sampled | Stage 1 pass | " + " | ".join(names) + " | Limit-rejected |",
             "|---|---|---|" + "---|" * (len(names) + 1)]
    for k, s in sorted(r["pole_sets"].items()):
        lines.append(f"| {k} | {s['sampled']} | {s['stage1_pass']} | "
                     + " | ".join(str(s["by_limit"].get(x, 0)) for x in names) + f" | {s['limit_rejected']} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratios", type=float, nargs="+", default=[8.0, 12.0, 15.0])
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    out = [count(r, args.n) for r in args.ratios]
    for r in out:
        print(table(r), "\n")
    if args.json:
        args.json.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
