"""Recommended worker count, projected map times and the result summary."""

from __future__ import annotations

RECOMMEND_SHARE = 0.95
SEARCH_CANDIDATES = 24


def recommended_workers(batches: list[dict]) -> int:
    """The smallest worker count whose throughput reaches RECOMMEND_SHARE of the best measured."""
    if not batches:
        raise ValueError("no batches")
    best = max(b["per_min"] for b in batches)
    return min(b["workers"] for b in batches if b["per_min"] >= RECOMMEND_SHARE * best)


def best_workers(batches: list[dict]) -> int:
    return max(batches, key=lambda b: b["per_min"])["workers"]


def choose_workers(batches: list[dict], tier: str) -> int:
    """The recommended worker count: in `quick` the better of the two measured, otherwise the smallest
    within RECOMMEND_SHARE of the best."""
    return best_workers(batches) if tier == "quick" else recommended_workers(batches)


def throughput_at(batches: list[dict], workers: int) -> float:
    """Solves per minute at `workers`: the largest measured batch with at most that many workers. When every
    measured batch is larger (a RAM cap below the smallest), the smallest one scaled linearly."""
    fitting = [b for b in batches if b["workers"] <= workers]
    if fitting:
        return max(fitting, key=lambda b: b["workers"])["per_min"]
    smallest = min(batches, key=lambda b: b["workers"])
    return smallest["per_min"] * workers / smallest["workers"]


def project(mesh_s: dict, single: dict, throughput_per_min: float, points: dict) -> dict:
    """Map times from the mesh time, the point count and the batch throughput. A `full` point costs
    `single["full"] / single["screening"]` screening points."""
    s_per_solve = 60.0 / throughput_per_min
    full_over_screening = single["full"] / single["screening"]
    screening_map_s = mesh_s["screening"] + points["screening"] * s_per_solve
    full_map_s = mesh_s["full"] + points["full"] * full_over_screening * s_per_solve
    return {"screening_map_s": screening_map_s, "full_map_s": full_map_s,
            "search_h": SEARCH_CANDIDATES * full_map_s / 3600}


def _rollup(steps: dict) -> dict:
    sources = [("correctness_points", steps["correctness_points"]["correctness"])]
    if "screening_map" in steps:
        sources.append(("screening_map", steps["screening_map"]["correctness"]))
    for name, entry in steps.get("full_maps", {}).items():
        sources.append((f"full_maps {name}", entry["map"]["correctness"]))
    statuses = [c["status"] for _, c in sources]
    status = "fail" if "fail" in statuses else "pass" if "pass" in statuses else "not checked"
    return {"status": status, "details": [f"{name}: {d}" for name, c in sources for d in c["details"]]}


def summary(steps: dict, tier: str) -> dict:
    """The headline numbers of a run, from the `steps` dict that `tiers.run_tier` fills. The recommended worker
    count is `steps["recommended"]["workers"]` (RAM-capped); without it, the uncapped choice for the tier."""
    batches = steps["batches"]
    best = best_workers(batches)
    recommended = steps["recommended"]["workers"] if "recommended" in steps else choose_workers(batches, tier)
    throughput = throughput_at(batches, recommended)
    single = {k: steps["single_solve"][k]["median"] for k in ("screening", "full")}
    projected = project({k: steps["mesh"][k]["seconds"] for k in ("screening", "full")}, single, throughput,
                        {k: steps["mesh"][k]["points"] for k in ("screening", "full")})

    measured_screening = steps.get("screening_map", {}).get("seconds")
    measured_full = steps.get("full_maps", {}).get("8_6", {}).get("map", {}).get("seconds")
    peaks = [b["peak_ram_gb"] for b in batches if b.get("peak_ram_gb") is not None]
    error = None
    if tier == "long" and measured_screening is not None and measured_full is not None:
        error = {"screening": (projected["screening_map_s"] / measured_screening - 1) * 100,
                 "full": (projected["full_map_s"] / measured_full - 1) * 100}

    def map_time(measured, value):
        return {"value": float(value if measured is None else measured), "measured": measured is not None}

    return {
        "single_solve_s": single["screening"],
        "single_solve_full_s": single["full"],
        "best_workers": best,
        "recommended_workers": recommended,
        "throughput_per_min": throughput,
        "best_throughput_per_min": max(b["per_min"] for b in batches),
        "peak_ram_worker_gb": max(peaks) if peaks else None,
        "throttle_pct": steps["sustained"]["throttle_pct"] if "sustained" in steps else None,
        "screening_map_s": map_time(measured_screening, projected["screening_map_s"]),
        "full_map_s": map_time(measured_full, projected["full_map_s"]),
        "search_h": projected["search_h"],
        "correctness": _rollup(steps),
        "srmweb_workers": recommended,
        "projection_error_pct": error,
    }
