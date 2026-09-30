# M4 handoff ("engine usable")

State: M1–M4b done (M4b on branch `m4b-map-runner`, merge pending); M4c next. NGSolve is the primary solver; `skfem_reference` is the independent cross-check. `maps/` holds `point.py`, `grids.py`, `run.py`, `dataset.py`, `pool.py` and `api.py` (`build_map`); `project/` is empty.

## Read first
- Spec §7 (maps, speed, checks), §10 (open items), §11 (decisions), M4 row of the milestone table (~line 301).
- `docs/team24-feasibility.md` (M3 finding), `docs/reference-machines.md`.

## M4 scope (spec milestone table)
Grids and fidelity presets; HDF5 datasets; persistent worker pool; cache; L_inc and ∂ψ/∂θ; inverse tables; overlap map and coupling check; standard results and key numbers; LUT exports (CSV, .mat); per-pole force arrays; all §7.3 checks; screening-vs-full fidelity check (within 3 %, Spearman ρ ≥ 0.95); error policy, cancellation, crash retry.

## Carried-in items (spec §10)
1. **Solve speed.** The cold 20 A `screening` solve takes 4.5–5.3 s against the 4 s gate (see table below). Decide first whether M4b attacks the gate; options are listed below the table.
2. **Air-gap element count.** 4 layers across the gap give 20–50k triangles even on `screening`. Measure DOF per preset. Add structured gap meshing if the speed budget needs it.
3. **L_inc factorisation.** Built on `sensitivity`, which refactorises the tangent. Reuse the Newton factorisation (about one Newton iteration saved per point with `with_l_inc=True`).
4. **Per-region stacking factor.** Currently per material. Revisit if rotor and stator differ.
5. **Deferred M2 minors:** `ramp_steps=0` crash; iterations counted only for the last attempt; basis cache keyed by array identity; pole-tip group missing from the saturation report.

## Rules to keep
- Import rules in `tests/test_import_rules.py`. `maps` may import all lower layers; only `solvers/` touches ngsolve/skfem.
- SI units. Frozen Pydantic models and dataclasses across layers.
- Fast suite under 10 min. Mark long tests `slow`. Unique test basenames.
- Do not change open-owner-decision behaviours (`self_starting`, `MIN_WEB_WIDTH`). Record decisions in spec §11.
- Comments describe the code as it is now, with no plan history.

## Suggested start (M4b)
1. Brainstorm, then write `docs/superpowers/plans/<date>-m4b-maps.md`.
2. Decide first whether to attack the 4 s gate, because it sets the grid sizes: structured air-gap mesh, scipy/umfpack tangent assembly, parallel points.
3. Then grids, datasets, workers.

## Speed measurements
8/6 screening mesh (42935 nodes), 20 A on phase A, `examples/solve_speed.py`, NGSolve, one thread. Timings vary ±30 % run to run.

| stage | cold 20 A | Newton it | sweep 5-10-20 A (warm) |
|---|---|---|---|
| baseline (residual assembled in NGSolve) | 9 s | 11 | not measured |
| numpy secant residual | 5.3 s | 11 | 26 it, 11.9 s |
| final run | 4.5–5.0 s (range over runs 4.5–5.3 s) | 11 | 26 it, 10.3 s |
| numpy tangent into NGSolve CSR, bulk netgen mesh | 2.0–2.5 s (three runs, first call includes the discretisation build) | 11 | 26 it, 4.7–5.0 s |

skfem_reference for comparison: cold 4.5–6.2 s (11 it), sweep 26 it, 9–12 s.

Gate (cold 20 A at θ = 0 in 4 s or less): **met** on NGSolve after the numpy tangent (2.0–2.5 s); before it, not met (4.5–5.3 s).

Remaining options, owner decides for M4b:
- structured air-gap meshing to cut DOF;
- scipy/umfpack tangent assembly (about 0.3 s per iteration);
- parallel map points;
- Euler current predictor (dropped in M4a): NGSolve cold with 1, 3, 6 sub-steps took 14 it 6.0 s, 8 it 4.8 s, 6 it 5.8 s against 11 it 4.5 s plain; warm sweep 24 it. skfem + Euler predictor (3 sub-steps) reached 3.5 s cold in one run; the predictor pays off only where the sensitivity solves are cheap.

## M4b: map times and M4c carry-in

8/6 `screening` map, I_max = 20 A, 8 angles x 8 currents = 64 points, NGSolve, one thread per worker, 16 logical CPUs, `examples/build_map_8_6.py`. The map time includes the parent's mesh build (about 4.6 s) and worker start-up.

| workers | wall | wall per point | Newton iterations | failed points |
|---|---|---|---|---|
| 4 | 68.5 s | 1.07 s | 0..14 | 0 |
| 8 | 50.4 s | 0.79 s | 0..14 | 0 |

Per-solve time, (wall - mesh) x workers / 64: about 4.0 s at 4 workers and about 5.7 s at 8, against 4.5 s for a single-process cold solve, so the per-worker slowdown from contention (memory bandwidth, shared cores) shows only at 8 workers.

Both maps came back with 64 OK points, peak Arkkio torque 12.04 N·m and a flux-linkage ratio (aligned to unaligned at 0.408 A) of 8.85. The 30 s `screening` budget (spec §7.2) is **not met**. With one job per angle there are only 8 jobs, so the wall time is set by the slowest angles (first job back after 34 s, last after 50 s on 8 workers) and more workers cannot help beyond 8. Options, owner decides for M4c:
- split jobs finer than one angle (per angle and current block) so more workers stay busy;
- structured air-gap meshing to cut DOF;
- scipy/umfpack tangent assembly;
- reuse of the Newton factorisation for L_inc when L_inc is added to the map.

Carried into M4c: L_inc and ∂ψ/∂θ in the dataset; per-pole force arrays; inverse tables; overlap map and coupling check; standard results and key numbers; LUT exports (CSV, .mat); the §7.3 checks; the screening-vs-full fidelity check (within 3 %, Spearman ρ >= 0.95); non-A excitation (needs the aligned angle per phase); the map open items in spec §10.
