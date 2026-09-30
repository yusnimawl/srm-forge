"""Screening-vs-full fidelity check: does the cheap preset rank and size designs like the full one?"""
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr

from ..model.design import Design
from .api import build_map
from .results import key_numbers

KEYS = ("la", "lu", "peak_torque", "psi_max")
MAX_REL_ERROR = 0.03
MIN_SPEARMAN = 0.95


@dataclass(frozen=True, eq=False)
class FidelityReport:
    designs: int
    rel_error: dict[str, np.ndarray]     # key number -> per-design |screening - full| / |full|
    spearman: dict[str, float]           # NaN with fewer than 3 designs
    ok: bool


def _preset(design: Design, preset: str) -> Design:
    return design.model_copy(update={"mesh": design.mesh.model_copy(update={"preset": preset})})


def fidelity_check(designs: Sequence[Design], i_max: float, *, solver: str = "ngsolve",
                   workers: int | None = None, cache_dir=None,
                   progress: Callable[[int, int], None] | None = None) -> FidelityReport:
    """Builds each design's screening and full map and compares `la`, `lu`, `peak_torque` and `psi_max`.
    `ok`: every relative error <= 3 % and, with 3 or more designs, every Spearman rho >= 0.95
    (a NaN rho from constant values fails)."""
    values = {p: {k: [] for k in KEYS} for p in ("screening", "full")}
    for d in designs:
        for preset, vals in values.items():
            dp = _preset(d, preset)
            key = key_numbers(build_map(dp, i_max, solver=solver, workers=workers, cache_dir=cache_dir,
                                        progress=progress), dp.machine)
            for k in KEYS:
                vals[k].append(getattr(key, k))
    scr = {k: np.array(v) for k, v in values["screening"].items()}
    full = {k: np.array(v) for k, v in values["full"].items()}
    rel = {k: np.abs(scr[k] - full[k]) / np.abs(full[k]) for k in KEYS}
    rho = {k: float(spearmanr(scr[k], full[k]).statistic) if len(designs) >= 3 else float("nan") for k in KEYS}
    ok = all(np.all(e <= MAX_REL_ERROR) for e in rel.values()) and (
        len(designs) < 3 or all(r >= MIN_SPEARMAN for r in rho.values()))     # NaN rho (constant input) fails
    return FidelityReport(len(designs), rel, rho, bool(ok))
