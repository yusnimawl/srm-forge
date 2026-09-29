# M4 handoff ("engine usable")

State: M1–M3 done, on `main`, tree clean. NGSolve is the primary solver; `skfem_reference` is the independent cross-check. `maps/` and `project/` are empty.

## Read first
- Spec §7 (maps, speed, checks), §10 (open items), §11 (decisions), M4 row of the milestone table (~line 301).
- `docs/team24-feasibility.md` (M3 finding), `docs/reference-machines.md`.

## M4 scope (spec milestone table)
Grids and fidelity presets; HDF5 datasets; persistent worker pool; cache; L_inc and ∂ψ/∂θ; inverse tables; overlap map and coupling check; standard results and key numbers; LUT exports (CSV, .mat); per-pole force arrays; all §7.3 checks; screening-vs-full fidelity check (within 3 %, Spearman ρ ≥ 0.95); error policy, cancellation, crash retry.

## Carried-in items (spec §10)
1. **`maps/point.py` `solve_point(...)`** returning a frozen `PointResult`. It wraps mesh_at_angle → machine_problem → solve → post, which every script and test repeats. Build this first.
2. **Solve speed.** About 0.65–1.0 s per Newton iteration at 43k DOF and 5–13 iterations cold, against a target of ≤ 4 s. Options:
   - vectorised P1 assembly with a fixed sparsity pattern;
   - parallel map points;
   - a tangent (Euler) predictor (warm and scaled starts do not help);
   - an energy (Armijo) line search, which saved only 5–30 %.
   Speed work applies to both adapters. Leave `skfem_reference` as it is.
3. **Air-gap element count.** 4 layers across the gap give 20–50k triangles even on `screening`. Measure DOF per preset. Add structured gap meshing if the speed budget needs it.
4. **L_inc** = ∂ψ/∂i, built on `SkfemReference.linearize` (consistent tangent).
5. **Phase labelling.** CCW motoring excites A→D→C→B. The owner decides whether to relabel; ask before the drive work.
6. **Per-region stacking factor.** Currently per material. Revisit if rotor and stator differ.
7. **Deferred M2 minors:** `ramp_steps=0` crash; iterations counted only for the last attempt; basis cache keyed by array identity; pole-tip group missing from the saturation report.

## Rules to keep
- Import rules in `tests/test_import_rules.py`. `maps` may import all lower layers; only `solvers/` touches ngsolve/skfem.
- SI units. Frozen Pydantic models and dataclasses across layers.
- Fast suite under 10 min. Mark long tests `slow`. Unique test basenames.
- Do not change open-owner-decision behaviours (`self_starting`, `MIN_WEB_WIDTH`). Record decisions in spec §11.
- Comments describe the code as it is now, with no plan history.

## Suggested start
1. Brainstorm, then write `docs/superpowers/plans/<date>-m4-maps.md`.
2. Task 1: `solve_point` and its test (both solvers agree at 1e-4).
3. Then the speed spike (item 2) before building grids, because it sets the grid sizes.

## Speed measurements
8/6 screening mesh (42935 nodes), 20 A on phase A, `examples/solve_speed.py`. Before: NGSolve with the secant residual assembled in NGSolve. After: numpy secant residual, NGSolve tangent.

| NGSolve | cold 20 A | Newton it | sweep 5-10-20 A (warm) |
|---|---|---|---|
| before | 9 s | 11 | not measured |
| after | 5.3 s | 11 | 11.9 s, 26 it |

skfem_reference for comparison: cold 6.2 s (11 it), sweep 12.1 s (26 it).
