r"""Speed benchmark for the §7.2 budgets: cold-cache map times on the 8/6 and 12/8 with 8 workers.

Run on an idle machine:  $env:PYTHONPATH="tests"; .venv\Scripts\python -u examples\speed_budget.py [--json PATH]
Items: screening = build_map + analyse_map (40 x 8); full = the same at 48 x 20; full_extras =
build_overlap_map + fem_checks (64 held-out samples) on the full map.
"""
import datetime
import json
import os
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

from conftest import make_8_6, make_12_8
from srmcore.maps import analyse_map, build_map, build_overlap_map
from srmcore.maps.fem_checks import fem_checks
from srmcore.model.design import Design, MeshSettings

WORKERS = 8
I_MAX = {"8_6": 20.0, "12_8": 10.0}          # docs/m5a-data/i_max.json
DESIGNS = {"8_6": make_8_6, "12_8": make_12_8}


def map_progress(label: str):
    """A progress callback that prints one line per 10 % of the map points."""
    step = [0]

    def report(done: int, total: int) -> None:
        if done * 10 >= (step[0] + 1) * total or done == total:
            step[0] = done * 10 // total
            print(f"{label}: {done}/{total} points", flush=True)
    return report


def cpu_name() -> str:
    """The CPU model; platform.processor() is empty on most Linux systems."""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def main() -> None:
    args = sys.argv[1:]
    out_path = Path(args[args.index("--json") + 1]) if "--json" in args else None
    runs = []
    for name, make in DESIGNS.items():
        for preset in ("screening", "full"):
            d = Design(machine=make(), mesh=MeshSettings(preset=preset))

            def job():
                r = build_map(d, I_MAX[name], workers=WORKERS, progress=map_progress(f"{name} {preset}"))
                analyse_map(r, d)
                return r

            r, s = timed(job)
            runs.append({"design": name, "item": preset, "seconds": s})
            print(f"{name} {preset}: {s:.0f} s", flush=True)
            if preset == "full":
                _, s = timed(lambda: (build_overlap_map(d, I_MAX[name], workers=WORKERS),
                                      fem_checks(d, r, workers=WORKERS)))
                runs.append({"design": name, "item": "full_extras", "seconds": s})
                print(f"{name} full_extras: {s:.0f} s", flush=True)
    result = {"srmcore": version("srmcore"), "cpu": cpu_name(), "logical_cpus": os.cpu_count(),
              "workers": WORKERS, "date": datetime.date.today().isoformat(), "runs": runs}
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
