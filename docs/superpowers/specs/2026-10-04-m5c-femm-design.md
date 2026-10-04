# M5c: FEMM cross-tool fixtures (design)

Goal: srmcore agrees with FEMM 4.2 within core spec §8.3 (ψ ±2 %, mid-range torque ±3 %, torque near alignment or in deep saturation ±5 %) on the Krishnan 8/6 and a 24/16 / 12/8 (core spec §2.3, §8.2 suite 4). FEMM is the reference value here: the check shows that an independent tool (its own mesher, solver and torque method) gets the same ψ and torque on the same geometry and B-H. Agreement with real machines is M5b and M5d.

## Owner decisions (2026-10-04)

1. **Krishnan 8/6 missing fields.** `slot_liner_thickness` 0.5 mm, `coil_inner_clearance` 1 mm, fillets 0, tapers 0. `fill_factor` 0.22, from the book's own data: 77 turns × 1.588 mm² = 122 mm² of copper in a 550 mm² coil side (fill only sets resistance, not ψ or T). Material M19 in both tools (the book's machine is M43; a cross-tool check only needs the same law on both sides). The validator passes.
2. **Second machine: both.** Jiang 24/16 (published, gaps assumed) and the synthetic 12/8 (`tests/conftest.py` `make_12_8`, complete geometry, no waivers).
3. **Jiang 24/16 assumed fields** (recorded as "assumed" in the fixture provenance): rotor pole height 20 mm (rotor yoke 0.0915 − 0.026 − 0.020 = 0.0455 m), rotor taper 5.5° (middle of the thesis's 3–8°), liner 0.3 mm, clearance 1 mm, stack 92 mm, the 1 mm pole-shoe fillet dropped (no topology counterpart), material M19 (10JNEX900 is not in the library yet). Built inside `waive_rules("self_starting")`; the validator flags nothing else. Stated values as in `docs/reference-machines.md` (turns 15, fill 0.54, stator taper 6°, stator yoke 15 mm, arcs 7.0°/7.2°).
4. **Boundary: A = 0 on the stator OD in both tools.** No outer air ring. The ring-default question stays open (core spec §11 2026-09-29, revisit in M5e).
5. **B-H handoff: the densely sampled srmcore law, LamFill 1.** FEMM gets `library_law(name).h_of_b` sampled at ≥ 300 points from 0 to 4 T (the effective, stacked curve including the tail towards Js), with lamination fill off. Both tools then solve with the same law. This supersedes the core spec §10 note "give FEMM the raw curve plus its LamFill" (§11 entry).

## Spike results (throwaway, Krishnan 8/6, 7 angles × 3, 13, 30 A)

- FEMM refinement levels L0/L1/L2 (each halves every size; L2 ≈ 310k nodes): L1→L2 moves ψ ≤ 0.18 % and torque ≤ 0.18 % of peak. L2 is converged to about 0.2 %.
- srmcore `full` vs FEMM L2: ψ ≤ 0.16 %, torque ≤ 0.61 % relative (where |T| ≥ 5 % of peak), ≤ 0.36 % of peak. `reference`: ψ ≤ 0.15 %, torque ≤ 0.23 % of peak. All 42 solves OK. Band noise is not a problem at these tolerances.
- Conventions match: torque positive counter-clockwise in both; `mo_getcircuitproperties("A")[2]` equals `PointResult.psi[0]` (Wb-turns, both poles, stack included); co-energy agrees. FEMM's interpolated B-H is within 0.022 % of `h_of_b` (FEMM smoothing never engages).
- Torque methods in FEMM, worst error vs srmcore `reference` in % of peak at L0/L1/L2: air-gap element 0.58/0.32/0.15; weighted stress tensor 0.81/0.29/0.23; co-energy difference ±0.5° (L1) 0.77 (remeshing noise, two solves per point: rejected). The stress tensor on a coarse mesh shows spurious torque at symmetric positions; the air-gap element is exactly symmetric.
- At 2° the rotor and stator pole corners coincide ((βr − βs)/2): slowest-converging point in both tools. Replaced by 4°.
- Aligned and unaligned torque is numerical noise (1e-4–1e-3 N·m) in both tools, so a relative error there is meaningless: a floor in % of peak is needed.

## Design

### 1. Machines (`tests/femm_machines.py`)
- `MACHINES: dict[str, Callable[[], Design]]` for `krishnan_8_6`, `jiang_24_16` (built inside `waive_rules("self_starting")`), `synth_12_8` (`make_12_8()`), all with `MeshSettings(preset="full")`, default `RegionMaterials` (stator/rotor M19, shaft steel_1010, coil copper), `outer_air_thickness` 0.
- `ASSUMED: dict[str, dict[str, str]]`: per machine, each assumed field and its reason (decisions 1 and 3), copied into the fixture provenance.
- `points(design) -> list[tuple[float, float]]`: (angle, current) pairs.
  - Angles: fractions (0, 4, 8, 15, 22, 28, 30)/30 of the unaligned angle π/Nr, each snapped to the band pitch of the `full` static mesh (`mesh_at_angle(static, θ).rotor_angle`), so FEMM and srmcore use the identical angle.
  - Currents: (0.4, 1.7, 3.9) × i_k, with knee current i_k = 1.5 T · g / (μ0 · N_pole) (aligned gap at 1.5 T with the MMF of one pole per gap), rounded to 2 significant figures. Krishnan: i_k = 7.75 A → 3.1, 13, 30 A, the spike's points.
- `tolerance(design, angle, current) -> float`: 0.03 when the angle is between 1/6 and 5/6 of the unaligned angle and current ≤ 1.7 i_k, else 0.05.

### 2. Fixture generator (`tools/femm_fixtures.py`, Windows only, run once)
`PYTHONPATH=tests .venv\Scripts\python tools\femm_fixtures.py [machine ...]` (pyfemm is a dev-only manual install, not a declared dependency; the script says so if it is missing).
- Geometry from `build_outline(design.machine)`: stator OD, stator inner boundary, coil sides; rotor boundary and shaft circle rotated by the snapped angle. One FEMM document per point, rebuilt from scratch. Arcs: compute the signed sweep, swap endpoints if negative (FEMM draws counter-clockwise). Units mm, planar, depth = stack length.
- Air gap: two construction circles at 1/3 and 2/3 of the gap.
- Materials: M19 and steel_1010 as ≥ 300 points of `h_of_b` on 0–4 T, LamFill 1; coil and air μr 1. A B-H probe check after one solve compares FEMM's B and H at ≥ 30 iron elements with `h_of_b`, skips points where H/B ≈ 1/μ0 (air), and fails above 0.1 %.
- Circuits: one series circuit per phase; each coil-side block on its phase circuit with turns `sign × turns_per_pole`; only phase A carries current.
- Boundary: A = 0 on the stator OD.
- Mesh levels L0, L1, L2, ...: level L uses gap element g/(3·2^L), iron 1.5 mm/2^L, slot air 3 mm/2^L, arc maxseg = size / radius (degrees), smartmesh off, minangle 30, precision 1e-9. Mesh sizes scale with the machine size: for machines other than the Krishnan 8/6, iron and slot-air sizes scale by bore radius / 50.3 mm.
- Two models per point:
  - **Air-gap-element model (primary torque):** both gap circles carry an air-gap boundary (BdryFormat 6), the middle third is labelled `<No Mesh>`, torque from `mo_gapintegral(name, 0)`.
  - **Meshed-gap model (ψ and cross-check torque):** the whole gap meshed, torque from the weighted stress tensor (`mo_blockintegral(22)`) on rotor iron + shaft, ψ from `mo_getcircuitproperties`.
  - ψ is recorded from both models; the fixture's ψ is the meshed-gap value.
- Convergence: run levels until the finest level that completes within 30 min per point. Keep the finest level F and F−1. FEMM's error estimate per point is |X_F − X_{F−1}|. The generator fails if, for any point, the ψ change exceeds 0.5 % or the torque change exceeds 0.5 % of the peak torque at that current, or if F < 1.
- Several FEMM processes run in parallel (distinct document names per process).
- Output: `tests/validation/fixtures/femm_<machine>.json`:
  - `provenance`: machine name, `design_json` (`Design.model_dump_json()`), `design_sha256`, `bh_sha256` (sha256 of the sampled (H, B) tables sent to FEMM, per material), `assumed` (from `ASSUMED`), srmcore version, FEMM build string, pyfemm version, mesh level F and its sizes, date, generator git commit.
  - `points`: list of {angle, current, tolerance, psi, torque_age, torque_wst, psi_prev, torque_age_prev, nodes} (SI units).

### 3. Slow test (`tests/validation/test_femm.py`, `@pytest.mark.slow`, parametrized over the three machines)
- Loads the fixture; rebuilds the design from `tests/femm_machines.py` and fails with "fixture stale, regenerate with tools/femm_fixtures.py" if `design_sha256` or `bh_sha256` (recomputed with the same sampling function, imported from `femm_machines.py`) differs.
- Solves srmcore `full` at every fixture point with NGSolve (`importorskip`; falls back to `SkfemReference` if NGSolve is missing), status must be OK or OK_WITH_FALLBACK.
- ψ: |ψ − ψ_FEMM| ≤ 0.02 · |ψ_FEMM|.
- Torque: T_pk(i) = max |torque_age| over the fixture's angles at that current; |T_arkkio − T_age| ≤ max(tol · |T_age|, 0.01 · T_pk(i)), tol from the fixture point.
- FEMM self-consistency: |T_age − T_wst| ≤ 0.01 · T_pk(i) at every point.
- Nothing in the fast suite (budget headroom about 40 s).

### 4. Results script (`examples/femm_check.py`)
Prints per machine the table point, ψ_FEMM, ψ error %, T_FEMM, T error % and % of peak, the tolerance used, and FEMM's own error estimate. Its output is the source of the results doc tables. Needs `PYTHONPATH=tests`.

### 5. Docs
- `docs/m5c-femm-results.md`: machines and assumed fields, FEMM settings and levels, B-H probe result, results tables, worst-case summary per machine against §8.3, deviations explained.
- Core spec: §10 FEMM note removed; §11 entry (2026-10-04) records decisions 1–5, the tolerance rule (floor 1 % of peak torque per current; mid-range = 1/6–5/6 of the unaligned angle at ≤ 1.7 i_k) and the result; §9 M5 row notes M5c done.
- `docs/reference-machines.md`: Krishnan 8/6 and Jiang 24/16 mapping tables gain the assumed values with "assumed (M5c)".
- `docs/m5-roadmap.md` and `CLAUDE.md`: M5c done, commands list gains `tools\femm_fixtures.py` and `examples\femm_check.py`.

## Out of scope
FEMM in CI (Windows-only COM, hours per machine; fixtures are deterministic, so committed results plus the staleness check give the same protection). Co-energy-difference torque. The outer air ring default. 10JNEX900 and M43 library curves (M5e).

## Done
Three fixtures committed with provenance; slow test green within §8.3 on all three; results doc with deviations explained; spec §11 entry.
