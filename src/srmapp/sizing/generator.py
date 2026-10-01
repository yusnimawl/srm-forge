"""Candidate generator: Latin-hypercube samples of radial SRM designs inside a bounded box (v0 spec §4.1)."""
import hashlib
import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc

from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import InputError
from srmcore.model.validator import require_valid
from srmcore.topology.radial import build_outline

from ..requirements import Requirements

POLE_SETS = ((6, 4, 3), (8, 6, 4), (12, 8, 3), (24, 16, 3))   # (stator poles, rotor poles, phases)
DEFAULT_MAX_OD = 0.35      # m
MIN_OD = 0.08              # m
_DIMS = 9
_TRIES_PER_DESIGN = 20     # sample budget per requested design before giving up on a pole set
_TURNS = (6, 120)


@dataclass(frozen=True)
class Candidate:
    id: str
    design: Design


def _machine(u: np.ndarray, ns: int, nr: int, m: int, d_lo: float, d_hi: float, max_speed_rpm: float) -> RadialSRMParams:
    d_o = d_lo + u[0] * (d_hi - d_lo)
    stack = d_o * (0.25 + 0.95 * u[1])
    d_r = d_o * (0.50 + 0.15 * u[2])
    gap = min(max(d_o / 400, 3e-4), 8e-4)
    limit = 2 * math.pi / (m * nr)              # Lawrenson self-starting limit on the pole arcs
    beta_s, beta_r = limit * (1.0 + 0.6 * u[3]), limit * (1.0 + 0.7 * u[4])
    w_s = 2 * (d_r / 2 + gap) * math.sin(beta_s / 2)
    w_r = d_r * math.sin(beta_r / 2)
    turns = int(round(math.exp(math.log(_TURNS[0]) + u[8] * (math.log(_TURNS[1]) - math.log(_TURNS[0])))))
    return RadialSRMParams(
        n_stator_poles=ns, n_rotor_poles=nr, n_phases=m,
        stator_outer_diameter=d_o, rotor_outer_diameter=d_r, air_gap=gap, stack_length=stack,
        shaft_diameter=d_r * (0.25 + 0.20 * u[7]),
        stator_pole_arc=beta_s, rotor_pole_arc=beta_r,
        stator_yoke_thickness=w_s * (0.5 + 0.4 * u[5]), rotor_yoke_thickness=w_r * (0.5 + 0.5 * u[6]),
        turns_per_pole=turns, fill_factor=0.5, slot_liner_thickness=4e-4, coil_inner_clearance=1e-3,
        lamination_thickness=0.35e-3, max_speed_rpm=max_speed_rpm)


def sample_candidates(req: Requirements, n: int, *, seed: int = 0,
                      pole_sets=POLE_SETS) -> tuple[list[Candidate], dict[str, int]]:
    """About `n` valid designs, split evenly over `pole_sets`. Designs the validator or the topology fit
    check rejects are dropped and counted; a pole set that cannot yield its share simply contributes fewer,
    so the result may hold fewer than `n` designs."""
    d_hi = req.max_outer_diameter_m or DEFAULT_MAX_OD
    d_lo = min(MIN_OD, d_hi / 2)
    base, extra = divmod(n, len(pole_sets))
    children = np.random.SeedSequence(seed).spawn(len(pole_sets))
    dropped = {"validator": 0, "fit": 0}
    kept: list[Candidate] = []
    for index, (ns, nr, m) in enumerate(pole_sets):
        per_set = base + (index < extra)
        samples = qmc.LatinHypercube(d=_DIMS, seed=np.random.default_rng(children[index])).random(
            max(per_set, 1) * _TRIES_PER_DESIGN)
        taken = 0
        for u in samples:
            if taken == per_set:
                break
            try:
                machine = _machine(u, ns, nr, m, d_lo, d_hi, req.max_speed_rpm)
                design = Design(machine=machine, mesh=MeshSettings(preset="screening"))
                require_valid(design)
            except InputError:
                dropped["validator"] += 1
                continue
            try:
                build_outline(machine)
            except InputError:
                dropped["fit"] += 1
                continue
            kept.append(Candidate(hashlib.sha256(design.to_json().encode()).hexdigest()[:12], design))
            taken += 1
    return kept, dropped
