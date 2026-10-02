# M4 handoff ("engine usable")

State: M1–M4 done (2026-09-30); M5 next. NGSolve is the primary solver; `skfem_reference` is the independent cross-check. `maps/` holds the map runner, dataset, pool, tables, checks, exports, overlap, fem_checks and fidelity modules; `project/` is empty. Sections below record the M4 history and measurements; the M5 carry-in is at the end.

## Read first (historical: written for M4)
- Spec §7 (maps, speed, checks), §10 (open items), §11 (decisions), M4 row of the milestone table (~line 301).
- `docs/team24-feasibility.md` (M3 finding), `docs/reference-machines.md`.

## M4 scope (spec milestone table)
Grids and fidelity presets; HDF5 datasets; persistent worker pool; cache; L_inc and ∂ψ/∂θ; inverse tables; overlap map and coupling check; standard results and key numbers; LUT exports (CSV, .mat); per-pole force arrays; all §7.3 checks; screening-vs-full fidelity check (within 3 %, Spearman ρ ≥ 0.95); error policy, cancellation, crash retry.

## Carried-in items (spec §10)
1. **Solve speed.** Resolved: the numpy tangent brought the cold 20 A `screening` solve to 2.0–2.5 s (gate 4 s met; see the table below).
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

## v0a grid study

Example 8/6, `screening` mesh, I_max 20 A, relative error against the 12 x 8 map.

```
    grid   T_peak       La    T@300   T@3000   T@9000  wall s   (rel. error vs 12x8)
  12x8      0.00%    0.00%    0.00%    0.00%    0.00%     154
   8x4      3.13%    6.33%   16.29%   22.26%   44.98%      53
  10x5      0.45%    4.47%   10.31%   13.63%   34.78%      85
  10x6      0.45%    2.71%   10.31%   13.71%   35.92%      95
  12x5      0.00%    4.47%    0.00%    0.27%    1.22%      93
  12x6      0.00%    2.71%    0.00%    0.15%    0.31%     101
```

Chosen stage-2 grid: 12 x 5 (`StageTwoGrid` default).

Caveats:
- The 12 x 8 reference shares its angle set with 12 x 5 and 12 x 6 (`angle_grid` depends only on the angle count), so their errors are current-interpolation error only; 0.00 % at T_peak and T@300 is by construction.
- Going from 12 to 10 angles at equal current count moves the envelope torque by 10 to 35 %, so the drive-model result is strongly sensitive to the angle count.
- 11 x N and 12 x 4 were not tried.
- A check of the 12-angle map against a 24 or 30 angle reference is open.

### v0a search run

`v0_search.py 24 6` (10 kW, 32 N.m, 3000 to 9000 rpm, 400 V, 20 A/mm2): sampled 24, dropped validator 2 / fit 3, stage 1 rejected 6, evaluated 6 in 1178 s (about 200 s per design). All six status ok; 0 of 6 feasible. Torque ratios 0.02 to 1.82, power ratios 0.01 to 0.56.

Open questions:
- Stage-2 time per design is about 10x the 20 s budget in the v0 spec.
- The stage-1 torque bound is optimistic against FEM.
- Power ratios are low. Analysis, not measurement: turns are sampled independently of bus voltage and max speed, and at fixed current density a turns change only rescales the same envelope in speed (flux linkage ~N, current ~1/N, resistance ~N^2), so a geometry may be fine with the wrong turn count. Choosing turns after the map is the follow-up (spec §9).

## v0a-2 stage-2 accuracy check (2026-10-01)

`python -u examples/v0_angle_check.py 4 20` (wire mode: Ø1.0 mm round, 2.0 x 1.0 mm rectangular, 60 x Ø0.1 mm litz; 150 A; 10 kW, 32 N.m, 3000 to 9000 rpm, 400 V; `full` mesh). One candidate per pole set, winding chosen on the default map (30 angles x 20 currents, N_THETA 181, 40 x 40 on/off grid); each variant changes one knob. Ratios: torque at base speed and worst power over base..max speed, against the requirement. Wall time 5.4 h (about 1 to 2 h per design, three `full` maps each).

```

839f971fc14d 6/4 OD 288 mm (3799 s)
  wire round, N 7, strands 21, R 13.1 mOhm
  variant         T ratio  P ratio       dT       dP
  default           1.063    1.068    0.00%    0.00%
  60 angles         1.061    1.067   -0.14%   -0.14%
  2x currents       1.063    1.069    0.01%    0.01%
  n_theta 361       1.071    1.077    0.80%    0.80%
  on/off 80         1.098    1.104    3.29%    3.29%

ffbcf554bae4 8/6 OD 202 mm (4316 s)
  wire rectangular, N 7, strands 10, R 8.7 mOhm
  variant         T ratio  P ratio       dT       dP
  default           1.040    1.046    0.00%    0.00%
  60 angles         1.051    1.056    1.03%    1.03%
  2x currents       1.040    1.046   -0.01%   -0.01%
  n_theta 361       1.040    1.045   -0.03%   -0.03%
  on/off 80         1.054    1.060    1.36%    1.36%

0e978852bf31 12/8 OD 225 mm (7086 s)
  wire round, N 9, strands 25, R 12.1 mOhm
  variant         T ratio  P ratio       dT       dP
  default           1.094    1.099    0.00%    0.00%
  60 angles         1.095    1.101    0.11%    0.11%
  2x currents       1.094    1.099    0.00%    0.00%
  n_theta 361       1.100    1.106    0.57%    0.57%
  on/off 80         1.106    1.112    1.12%    1.12%

7dea4b9c6854 24/16 OD 147 mm (4206 s)
  wire round, N 4, strands 11, R 21.6 mOhm
  variant         T ratio  P ratio       dT       dP
  default           0.519    0.522    0.00%    0.00%
  60 angles         0.518    0.521   -0.25%   -0.25%
  2x currents       0.519    0.522   -0.00%   -0.00%
  n_theta 361       0.521    0.524    0.32%    0.32%
  on/off 80         0.526    0.528    1.25%    1.25%
```

Findings:
- Turns after the map works: 3 of 4 candidates are feasible (6/4, 8/6, 12/8; ratios 1.04 to 1.10). The 24/16 at OD 147 mm reaches 0.52 at its best winding (geometry too small for 32 N.m), and is reported as the closest winding, not dropped.
- 60 against 30 angles: -0.25 to +1.03 %. 2x currents: within 0.01 % (the exact wire-mode map range keeps current resolution adequate). N_THETA 361: -0.03 to +0.80 %.
- The on/off grid is the largest error source: 80 x 80 against 40 x 40 gives +1.12 to +3.29 %, always upward (the coarse grid misses the best firing angles). The 6/4 exceeds the 2 % limit of the v0a-2 spec §5. Owner decision: raise the default on/off grid (scan time only, no FEM). Not changed.
- The selection rules put chosen designs close to ratio 1.0, so a few percent of drive-model error can flip feasibility. Owner decision: a feasibility margin. Not changed.

## Small-cycle accuracy check (2026-10-02)

`python -u examples/v0_angle_check.py` (4 candidates, 20 currents) on branch `small-cycle-rms-paths`, at the search defaults: margin 1.05, `j_limit` 20 A/mm2 on the RMS current, peak cap 40 A/mm2, parallel paths, 80 x 80 on/off grid. Same requirement and wires as the v0a-2 check. Wall time about 5.3 h (the map range doubled with the peak cap, so the maps were rebuilt). Log: `out/angle_check_small_cycle.log`.

| Design | Winding | J_rms A/mm2 | Default T / P ratio | 60 angles | 2x currents | N_THETA 361 | On/off 160 vs 80 (at N_THETA 361) |
|---|---|---|---|---|---|---|---|
| 6/4 OD 288 | round, N 7, paths 1, strands 21, 13.1 mOhm | 5.8 | 1.097 / 1.103, feasible | -0.13 % | +0.04 % | -0.04 % | +0.8 % |
| 8/6 OD 202 | rect., N 7, paths 1, strands 10, 8.7 mOhm | 4.9 | 1.054 / 1.060, feasible | +1.01 % | +0.02 % | +0.60 % | +0.6 % |
| 12/8 OD 225 | round, N 9, paths 1, strands 25, 12.1 mOhm | 4.8 | 1.106 / 1.112, feasible | +0.14 % | +0.01 % | -0.49 % | +0.5 % |
| 24/16 OD 147 | round, N 13, paths 2, strands 3, 64.3 mOhm | 18.9 | 0.757 / 0.761, infeasible | -0.02 % | 0.00 % | -0.41 % | +0.1 % |

The on/off column is the "361, on/off 160" row against the "n_theta 361" row.

Findings:
- The 80 x 80 on/off grid is within 0.8 % of 160 x 160 on every design (limit 2 %, decision §10 (a) met). Every other variant stays within 1.01 %.
- The 6/4, 8/6 and 12/8 windings are the same as in the v0a-2 check; their ratios rose by 1 to 3 % from the finer on/off grid alone. All three pass the 1.05 margin. The 8/6 passes by 0.4 %, inside the 60-angle effect (+1.0 %), and the variants all move its ratios up, so the default settings err on the low side.
- J_rms of the three feasible designs is 4.8 to 5.8 A/mm2 at a 150 A peak. The RMS limit does not bind; their windings are set by the lowest-resistance rule.
- The 24/16 improves from 0.52 to 0.76: with the limit on the RMS current, it takes 13 turns on 2 paths, a peak density of about 25 A/mm2 and J_rms 18.9 A/mm2, close to the limit. The geometry is still too small for 32 N.m.
