# R5a: Thermal solver and rotor stress core

Merged 2026-11-09, PR #23. Versions after the merge: srmcore 0.7.0 (unchanged).
Spec `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md`. Plan `docs/superpowers/plans/2026-11-07-r5a-thermal-stress-core.md`. Detailed results `docs/r5-thermal-results.md`, sources `docs/r5-sources.md`.

## Goal

Build the 2D thermal solver and the analytic rotor stress model, and pass gates V1 (solver against closed forms) and V6 (stress against an elastic FE). R5 as a whole is done when ratings and stress render on an 8/6 and a bench-target case.

## What shipped

- Optional `thermal` and `mechanical` blocks in material files, kept out of `maps.identity.material_digest` so no map hash changes.
- `srmcore.thermal` (`domain`, `model`, `solve`): P1 conduction on the static mesh coupled to lumps, steady state and backward-Euler transient, `ThermalRunaway` above 1000 degC.
- `srmcore.post.rotor_stress`: bore and pole-root stress at 1.2 x speed, safety factor, speed limit and `gap_closure`. Statuses `ok`, `no_strength_data`, `no_fillet`, `kt_out_of_range`, `imported_iron`.
- `tools/rotor_stress_sweep.py` (FE sweep and fit) and `tools/rotor_stress_literals.py`.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| V1, slab with Robin ends | 2.7e-15 of the rise on the centre row (gate 1e-9) | `tests/thermal` |
| V1, manufactured solution order | error ratio 3.99 (gate over 3) | `tests/thermal` |
| V6, first model | root 36 to 47 % low: failed | FE sweep |
| V6, revised model, 1447 held-out designs | worst peak -3.44 %: passed | 2D elastic FE, converged under 0.1 % |
| Tip growth against the FE | up to 9.4 % low (lattice), 7.8 % low (held-out) | same |
| Search-candidate coverage of the validity box | about 82 % | held-out set |
| Slow V6 test | about 17 min | 16 cores |
| Fast suite | 1565 passed | PR #23 |

## Decisions

- 2026-11-05, owner: 10JNEX900 rotor strength is the cited yield of 570 MPa (Ou et al. 2021), checked as ductile at grade B.
- 2026-11-07, builder: thermal and mechanical blocks stay out of the material digest (a new block would have missed every cached map).
- 2026-11-09, builder: the FE reference is a curved half-pole sector, and the root model gained six FE-fitted constants.
- 2026-11-09, builder: the validity box is cut with joint limits, taper limited to +-1.5 deg.
- 2026-11-10, owner: the six FE constants are accepted.

## Open after this step

- Tip growth reads low, the unsafe sign. R5b carries it as a budget row.
- Iron specific heat, expansion and through-stack conductivity of 10JNEX900 were not found (tracker 10d).
- Gates V0, V2, V4, V5 and the Kiyota 18/12 check wait for R5e.

## Evidence

CI green on Windows and Linux. The held-out list was committed at 37303cd before any FE ran on it. A review found box corners reading up to 10.9 % unsafe, which led to the joint limits. Rotor fillet radius is never set by the candidate generator at this step (fixed 2026-11-10).
