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
- `self_starting` stays a hard error for user designs (reference machines use `waive_rules`); record decisions in spec §11.
- Comments describe the code as it is now, with no plan history.

## Suggested start (M4b)
1. Brainstorm, then write `docs/superpowers/plans/<date>-m4b-maps.md`.
2. Decide first whether to attack the 4 s gate, because it sets the grid sizes: structured air-gap mesh, parallel points.
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
- parallel map points;
- Euler current predictor (dropped in M4a): NGSolve cold with 1, 3, 6 sub-steps took 14 it 6.0 s, 8 it 4.8 s, 6 it 5.8 s against 11 it 4.5 s plain; warm sweep 24 it. skfem + Euler predictor (3 sub-steps) reached 3.5 s cold in one run; the predictor pays off only where the sensitivity solves are cheap.

## M4b: map times and M4c carry-in

8/6 `screening` map, I_max = 20 A, 8 angles x 8 currents = 64 points, NGSolve, one thread per worker, 16 logical CPUs, `examples/build_map_8_6.py`. The map time includes the parent's mesh build (about 4.6 s) and worker start-up.

| workers | wall | wall per point | Newton iterations | failed points |
|---|---|---|---|---|
| 4 | 68.5 s | 1.07 s | 0..14 | 0 |
| 8 | 50.4 s | 0.79 s | 0..14 | 0 |
| 4, per-point jobs + numpy tangent | 51.3 s | 0.80 s | 0..14 | 0 |
| 8, per-point jobs + numpy tangent | 45.9 s | 0.72 s | 0..14 | 0 |
| 8, + L_inc and pole forces per point | 51.6 s | 0.81 s | 0..14 | 0 |

The last two rows use one pool job per (angle, current) point, highest current first, and the numpy tangent. The 30 s budget is **still not met**: per-solve time, (wall - mesh) x workers / 64, is about 5.2 s at 8 workers and 6.4 s at 4 against 2.0-2.5 s for a single-process cold solve, so the pool run is dominated by per-worker slowdown under contention (and worker start-up), not by load balance.

Per-angle baseline (first two rows): per-solve time, (wall - mesh) x workers / 64, was about 4.0 s at 4 workers and about 5.7 s at 8, against 4.5 s for a single-process cold solve. Both maps came back with 64 OK points, peak Arkkio torque 12.04 N·m and a flux-linkage ratio (aligned to unaligned at 0.408 A) of 8.85. With one job per angle there were only 8 jobs, so the wall time was set by the slowest angles (baseline).

Pool contention (measured by the controller, pooltime script, 64 jobs, i7-13620H laptop: 6 performance and 4 efficiency cores, 16 threads): mean per-job time 1.63 s at 1 worker, 1.85 s at 2, 2.63 s at 4, 4.44 s at 8; the serial map takes 109 s. The per-solve slowdown in the pool, including the rise from 4.0 s to 6.4 s at 4 workers, comes from CPU contention (hybrid cores, shared power limit, memory bandwidth). It is not load balance and not code.

Remaining options to reach 30 s, owner decides:
- reuse umfpack's symbolic factorisation (`inverse.Update()`): 0.078 s vs 0.100 s per factorisation, about 8 % per solve;
- fewer air-gap layers, which needs the validator's `min_layers` rule (at least 4) relaxed;
- coarser slot-air grading in the screening preset: slot_air plus rotor_slot_air hold 31.6k of the 85.7k triangles (M5 preset study).

Carried into M4c: L_inc and ∂ψ/∂θ in the dataset; per-pole force arrays; inverse tables; overlap map and coupling check; standard results and key numbers; LUT exports (CSV, .mat); the §7.3 checks; the screening-vs-full fidelity check (within 3 %, Spearman ρ >= 0.95); non-A excitation (needs the aligned angle per phase); the map open items in spec §10.

## M4c: fidelity and full-map checks

Run: `examples/fidelity_8_6.py` (4 variants of the example 8/6, I_max 20 A, ngsolve, default workers), 2752 s wall for 8 maps. Tolerances unchanged (rel. error <= 3 %, Spearman >= 0.95).

| stator/rotor arc | la | lu | peak_torque | psi_max |
|---|---|---|---|---|
| 18/22 | 2.59 % | 0.07 % | 6.67 % | 0.02 % |
| 20/22 | 2.83 % | 0.07 % | 3.23 % | 0.04 % |
| 22/24 | 3.00 % | 0.09 % | 1.22 % | 0.03 % |
| 20/24 | 2.79 % | 0.08 % | 1.70 % | 0.04 % |
| Spearman | 1.000 | 1.000 | -0.400 | 1.000 |

**Fidelity: FAIL.** Peak torque is off by up to 6.67 % (3.23 % on the base design) and ranks the designs wrongly (rho -0.4); `la` sits at the 3 % limit (3.00 % is the worst, the check is `<= 0.03` on the unrounded value). `lu` and `psi_max` are well inside. Screening with 8 angles is not a reliable torque guide. The 53-69 s screening wall times in this run ran alongside other work; the reference screening timings are in the speed table (46-52 s on 8 workers).

Cause, measured by rebuilding the screening maps with more angles (same screening mesh, 8 currents), rel. error against the `full` map:

| stator/rotor arc | angles | la | lu | peak_torque | psi_max | wall |
|---|---|---|---|---|---|---|
| 18/22 | 12 | 2.59 % | 0.07 % | 0.07 % | 0.02 % | 99 s |
| 20/22 | 12 | 2.83 % | 0.07 % | 0.10 % | 0.04 % | 100 s |
| 22/24 | 12 | 3.00 % | 0.09 % | 0.24 % | 0.03 % | 88 s |
| 20/24 | 12 | 2.79 % | 0.08 % | 0.21 % | 0.04 % | 70 s |
| 18/22 | 16 | 2.59 % | 0.07 % | 0.04 % | 0.02 % | 105 s |
| 20/22 | 16 | 2.83 % | 0.07 % | 0.21 % | 0.04 % | 115 s |
| 22/24 | 16 | 3.00 % | 0.09 % | 0.65 % | 0.03 % | 112 s |
| 20/24 | 16 | 2.79 % | 0.08 % | 0.75 % | 0.04 % | 87 s |

- The peak-torque error comes from the 8-angle grid missing the torque peak: 12 angles bring it under 0.25 %. The peak value is the grid maximum; a dense evaluation of the periodic angle spline on the 8-angle grid overshoots instead (1.7-5.3 %), so it is no fix.
- The `la` error (2.6-3.0 %) does not change with the angle count: it comes from the screening mesh (aligned-position saturation at the pole tips) and needs a finer screening mesh or a looser La tolerance.
- The four variants' `full` peak torques span only 12.40-12.44 N·m (0.3 %), far less than the 8-angle error, so the Spearman -0.4 on peak torque says the variants are too alike to rank, not only that screening is wrong.
- The wall times above ran partly alongside the test suite; treat them as upper bounds. A 12-angle screening map costs about 1.5 × the 8-angle map.

Owner decision (2026-09-30): `screening` is 12 angles × 8 currents, the screening La tolerance is 5 %, the speed budgets are re-baselined to these laptop numbers, and the held-out torque limit is 3 % until the M5 convergence study (spec §11). With 12 angles the 8/6 golden peak torque is 12.42 N·m against 12.44 N·m on the `full` map.

Wall times per map (default workers): screening 53-69 s (64 points, budget 30 s: missed); `full` 520, 719, 717, 552 s (600 points, budget 5 min = 300 s: missed on all four).

Checks on the base design's (20/22) cached `full` 30x20 map:
- `analyse_map`: passes; `iron_b_peak` 1.481 × Js (warned against the old 1.15 limit; passes the 1.5 limit decided on 2026-09-30).
- `fem_checks` wall 33 s against the 7 min "full extras" budget: met.
- `held_out_psi` 5.7e-4 (limit 5e-3): pass. `held_out_torque` 0.0211 (limit 0.01): **FAIL**. `band_radius` 8.2e-4 (limit 0.01): pass.

## M5 carry-in

What M5 inherits from M4:
- A working engine: `build_map`, `build_overlap_map`, `analyse_map`, exports, `fem_checks`, `fidelity_check`; goldens for the 8/6 screening map in `tests/maps/goldens_8_6.json`.
- Open owner decisions (spec §10, "Open items after M4"): map speed against the 30 s and 300 s budgets, the failing screening fidelity check (preset refinement or a different rule), held-out torque on the default `full` grid, the provisional check limits.
- Deferred: the saturation-knee-vs-Bsat check; reuse of the Newton factorisation for L_inc (about 0.15 s per point); temperature in the cache key; engine changes enter the cache key only through the srmcore version.
- Iron B peaks reach 1.43–1.48 Js at the pole-tip corners on the example 8/6 (limit 1.5 Js); the material data behind that is provisional (spec §10).
- M5 work: FEMM fixtures, TEAM 24 comparison, measured-data comparison, mesh-preset defaults from a convergence study (which also addresses the fidelity result), uncertainty budgets.
