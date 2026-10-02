# M5a: mesh convergence study and preset defaults

Status: approved in brainstorming (2026-10-02). Parent: core spec `2026-09-28-srm-core-engine-design.md` §4.5, §7.3, §8.3–8.4, §9.

## 1. Goal

Measure the discretisation error of the `screening`, `full` and `reference` mesh presets and of the map grids, then set their defaults from the data. The result is the first defensible error bar on every map ("`full` is within X % of the converged answer"), and an input to the M5 uncertainty budget (§8.4) and to the search margin (1.05).

Out of scope (decided 2026-10-02): the adaptive `reference` preset (moved to M5e, and only built if a later need appears), nested mesh refinement, P2 elements, FEMM, TEAM 24, measured data.

## 2. Evidence from the spike (2026-10-02)

Throwaway spike on the conftest 8/6 (1 mm fillets), ngsolve, every resolved length scaled by 2^(−k/2), k = 0…5 (43k to 1.22M nodes), fit q = q∞ + C·h^p over the six levels:

| quantity | p | screening | full | k = 5 |
|---|---|---|---|---|
| ψ aligned 1 A | 1.7 | −0.27 % | −0.22 % | −0.01 % |
| ψ aligned 20 A | 2.0 | −0.08 % | −0.04 % | −0.00 % |
| ψ unaligned 1 A | 1.8 | −0.37 % | −0.28 % | −0.02 % |
| ψ mid (10°) 1 A | 1.8 | −0.40 % | −0.31 % | −0.02 % |
| ψ mid 20 A | 1.9 | −0.15 % | −0.12 % | −0.01 % |
| torque mid 20 A, % of peak | ~0.6, non-monotone | +0.14 % | −0.06 % | +0.06 % |

Findings:
- The screening La error of 2.6–3.0 % (M4c) is a definition artefact: La is the secant at `currents[1]`, which is 0.41 A on the 8-current grid and 0.055 A on the 20-current grid. At equal current the two presets agree to 0.05 %.
- Mesh error is already far inside the §8.3 tolerances on both presets. `full` has only 15 % more nodes than `screening` and is barely more accurate.
- ψ converges cleanly (p ≈ 1.7–2.0), so the fit is valid for flux. Torque converges erratically but its whole mesh error is ≤ 0.15 % of peak.
- Uniform refinement reaches a 0.02 % ψ truth at 1.22M nodes (3.8 GB, 4–12 min per point). 2.4M nodes pages on the 16 GB laptop.
- `gmsh.model.mesh.refine()` keeps new boundary nodes on the CAD arcs (nested refinement is possible if ever needed).
- The held-out torque error (2.1 % on the 8/6 `full` map, M4c) is about 15× the mesh error, so the map grid or band noise dominates, not the mesh.

## 3. Engine changes

### 3.1 La/Lu at a fixed current
- `maps/grids.py`: `LA_CURRENT_FRACTION = 0.05`. `current_grid(i_max, n, exponent)` returns the n power-law points plus `LA_CURRENT_FRACTION · i_max`, sorted (n + 1 points; no duplicate if it already falls on a node). `GRID_SIZES` keeps its meaning: the power-law count.
- `maps/results.py` `key_numbers`: La and Lu are the secant ψ/i at the grid current equal to `LA_CURRENT_FRACTION · I_max` (I_max = last grid current), found with `np.isclose`. A map without that current raises `ValueError` naming it. Docstrings state the definition.
- Every other `currents[1]` use is checked and moved to the same rule where it means "lowest non-zero current" for La/Lu.

### 3.2 Provenance hashes the resolved mesh settings
`maps/dataset.py` `provenance` adds `"mesh_resolved"`: the `ResolvedMeshSettings` of the design as plain JSON (sizes, refinement, band divisions, quality limits). Changing a preset's numbers or the sizing code's output then changes the hash, so stale cached maps are misses.

### 3.3 `MeshSettings.scale`
- New field `scale: float = 1.0`, `gt=0`. In the design JSON, so in provenance.
- `resolve_mesh_settings` applies it last, to the resolved preset and user values alike: every region size, the gap size and every refinement size × scale; every growth g → 1 + (g − 1)·scale (keeps the grading self-similar); band divisions → `base · max(1, round(divisions / scale / base))` with base = lcm(Ns, 2·Nr), so aligned and unaligned positions stay on the band grid. An explicit `airgap_circumferential_divisions` is used as given (the user pinned it; the study pins it per level so its angles stay on every grid). Band divisions are only re-rounded when `scale != 1`.
- `scale = 1` reproduces today's meshes exactly (test).

## 4. Study

### 4.1 `examples/mesh_convergence.py`
Public API only (`build_machine_mesh`, `solve_point`, `make_solver`, `resolve_mesh_settings`). Arguments: design name(s), level range. Appends one JSON line per (design, level) to a results file and prints ASCII only; a second mode reads the file, fits and writes `docs/m5a-convergence.md` plus PNG plots (error vs node count per quantity, Arkkio − virtual-work gap vs node count).

- Designs: conftest 8/6, 12/8, 24/16, and the 8/6 with both fillet radii 0.
- Levels: `MeshSettings(preset="screening", scale=2**(-k/2))`, k = 0…5; plus the stock `screening`, `full` and `reference` presets as extra rows. If a design's finest level does not fit in memory, its finest feasible level is the last.
- I_max per design: 20 A for the 8/6 variants (as in M4); for the others, doubling from 5 A on the `screening` mesh at the aligned angle until the stator-pole peak |B| (`saturation_report`) reaches 2.0 T. Stated per design in the report.
- States: aligned (0), unaligned (τ/2), τ/12 and τ/6 (partial overlap), τ = 2π/Nr; currents i_La and I_max. Each level pins `airgap_circumferential_divisions` to the nearest multiple of B = lcm(Ns, 2·Nr, 12·Nr) to the scaled default, so every state angle is on every level's band grid. Quantities: ψ, Arkkio and virtual-work torque, W′.
- Fit: least-squares q = q∞ + C·h^p over all levels (h = scale). Report p, q∞, fit residual, and for torque the value relative to peak torque. Flag quantities with p outside [0.5, 3] or a non-monotone series; for those the error bound is the finest-level spread × 3 (GCI safety factor), not the extrapolation.

### 4.2 Grid-error split (`full` preset, each design)
Run alongside the study, in the same script:
- angle-only: held-out angles at grid currents; current-only: grid angles at held-out currents; both against the map interpolant (as `fem_checks` builds it).
- band noise: a torque sweep at I_max over 4 band pitches around mid-stroke at 8 points per pitch; noise = RMS residual of off-pitch points against a cubic fit of the on-pitch points, relative to peak torque.

### 4.3 Running
Long runs launch detached with `python -u` and are watched (handoff process notes). Expected cost: about 1–1.5 h per design for the convergence series, plus a `full` map and the split per design.

## 5. Decisions from the data (exit criteria)

Targets, worst case over the four study designs, against q∞ (torque as % of peak):

| preset | ψ, La, Lu | torque |
|---|---|---|
| `screening` | ≤ 2 % | ≤ 3 % |
| `full` | ≤ 0.5 % | ≤ 1 % |
| `reference` | ≤ 0.1 % | ≤ 0.2 % |

- Each preset's default is the cheapest setting that meets its target with a factor-2 margin on every design. `reference` becomes `full` at a fixed `scale` if that is cheapest.
- Grid sizes (`GRID_SIZES`) and the held-out torque limit are set from §4.2: the limit is the measured `full` held-out error with a factor-1.5 margin, but at most 3 %. If band noise dominates, the report says so and an owner item is added rather than tightening the limit.
- The fidelity check's La tolerance returns to 3 % if the §3.1 fix removes the artefact (measured).
- Afterwards: regenerate `tests/maps/goldens_8_6.json`, bump the srmcore version, run `examples/v0_search.py` before and after on the same settings and report rank changes and feasibility flips, update spec §4.5 (preset defaults), §10 and §11, `docs/m4-handoff.md` caveats, and `CLAUDE.md`.

## 6. Tests

- `current_grid` contains `0.05·i_max` exactly once and stays sorted; `key_numbers` uses it; a map without it raises.
- `provenance` changes when a preset's resolved sizes change (monkeypatched `PRESETS`) and is unchanged otherwise.
- `scale = 1` leaves `resolve_mesh_settings` unchanged; `scale = 0.5` halves every size, halves the growth excess, doubles band divisions and keeps them a multiple of lcm(Ns, 2·Nr).
- All new tests fast and small. The fast suite stays under the 10 min budget; if it does not, mark or trim `tests/app` tests first.

## 7. Risks

- Sharp corners (fillet 0) may converge much slower than the spike's filleted 8/6; that is why the series includes them, and the targets apply to them too.
- Changing presets moves every cached map and every srmapp result; §5's before/after run makes that visible.
- Torque's erratic convergence makes its q∞ uncertain; the GCI fallback bounds it.
