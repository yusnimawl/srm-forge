# M5b: TEAM Problem 24 comparison (design)

Goal: the magnetostatic TEAM 24 comparison counts as validation evidence (core spec §2.3, §8.2 suite 5), reported as error ± uncertainty against the published measurements.

## Owner decisions (2026-10-04)

1. **Table I units: H in ×10⁴ A-t/m.** The printed table header reads "(×10⁴ A-t/m)" with entries 00.400 … 39.634, and Fig. 3's H axis runs 0 … 4.0 ×10⁵ A/m with the curve at 2.47 T near 4×10⁵. So H = 4 000 … 396 340 A/m. The fixture's earlier reading (400 … 39 634 A/m, from the NGSolve TEAM 24 page) was 10× too soft and is replaced. With the correct reading, J = B − μ0·H rises to 1.979 T at point 17 (240 kA/m) and then dips by up to 5 mT (points 18–21), which is at the digitisation level of the table.
2. **No pass/fail gate against the measurement.** The 2D magnetostatic model omits two effects of known sign: 3D end flux (axial length 25.4 mm ≈ 9× the 2.7 mm gap; lowers 2D ψ and torque) and eddy currents in the solid steel (σ = 4.54 MS/m; slow the measured current rise). The comparison is reported with error and an uncertainty budget. The slow test pins the 2D result (regression), checks the expected signs and a sanity band of 25 %. The M5d end-effect hook, calibrated on the Krishnan machine, is later applied to TEAM 24 as an independent check of the hook.
3. **Current-rise deviations: accepted, attributed.** With the corrected B-H the model runs up to +18 % ahead of the measurement between 5 and 50 ms, and the 2 ms point is −1.7 %. Both omitted effects push the model current ahead of the measurement; no further investigation in M5b.
4. **Rotor-pole flux (Table V) is compared** in the results table, not gated.

## Spike results (throwaway, NGSolve, default mesh)

| Quantity | Model | Measured | Error |
|---|---|---|---|
| Static torque at 7.41 A (Arkkio) | 2.800 N·m | 3.22 | −13.1 % |
| ψ(7.41 A) | 0.3676 Wb-turns | — | — |
| Current, max |error| for t ≥ 5 ms | — | Table III | +18.6 % (at 20 ms) |
| Torque at the measured current | — | Table IV | −7.5 … +10.2 … −13.1 % |

Sensitivities: Js 1.98–2.05 T and truncate-vs-clamp of the J dip: < 0.01 % (peak iron B 2.29 T, barely in the tail). Mesh size ×0.5: torque 0.004 %. R 3.09 vs 3.12 Ω and Table II voltage vs constant 23.1 V: ≤ 1 % on current.

## Design

### 1. Fixture (`tests/team24_fixture.py`)
- `H_TABLE` in A/m from the ×10⁴ reading; keep Table I points 1–17 and drop 18–21 (J dips after its peak; `process_bh` requires J non-decreasing). A comment states the reason and the 5 mT size of the dip.
- `ASSUMED_JS = 2.0` T (above the 1.979 T at point 17), with a comment that results move < 0.01 % over 1.98–2.05 T.
- Measured data move from the example into the fixture: Table II (voltage), III (current), IV (torque), V (rotor-pole flux, ×10⁻⁴ Wb).
- `current_rise(psi_of_i, times, resistance, voltage)`: integrates di/dt = (V(t) − R·i)/ψ′(i) on a PCHIP ψ(i) map with `solve_ivp`; `voltage` is a constant or a callable (Table II interpolation).
- `rotor_pole_flux(problem, solution)`: flux through the rotor pole on the chord perpendicular to the pole axis at 8.7 mm below the rotor tip circle (search coil position, Fig. 1), = depth × (A(p₁) − A(p₂)) with p₁, p₂ just outside the two pole flanks, A interpolated on the P1 mesh with `matplotlib.tri.LinearTriInterpolator`. Assumption (stated in the results doc): Table V is flux per turn (the figure is labelled "rotor pole flux (Wb)"), and the coil sits on the rotor pole under the top stator pole; both rotor poles carry the same flux by symmetry.

### 2. Slow test (`tests/validation/test_team24.py`, `@pytest.mark.slow`)
- Cross-solver agreement at 7.41 A: A, ψ, energy, Arkkio torque ≤ 1e-4 relative (NGSolve via `importorskip`).
- Arkkio vs virtual-work torque ≤ 0.1 %.
- Regression: torque and ψ at 7.41 A pinned at rel 1e-3 to the values recorded in the results doc.
- Measurement checks: static torque error < 0 and |error| < 25 %; model current ≥ measured at every Table III time from 5 to 100 ms; |current error| < 25 % at every Table III time.
- One ψ(i) map built once per module (fixture scope), reused by the current checks.
- Nothing is added to the fast suite (budget headroom is ~40 s).

### 3. Script (`examples/team24_check.py`)
Prints: solver agreement; static torque and ψ; current table (model vs Table III); torque vs time (via model current) and torque vs measured current (T(i_meas), removes the time-axis error); rotor-pole flux vs Table V (vs time via model current and vs measured current); sensitivity rows (R 3.09/3.12 Ω, constant vs Table II voltage, Js 1.98/2.0/2.05 T, mesh scale 1 and 0.5). Its output is the source of the results doc tables.

### 4. Docs
- `docs/m5b-team24-results.md` replaces `docs/team24-feasibility.md` (deleted; the feasibility doc's input table and geometry choices move across, its B-H and result sections are rewritten). Contents: inputs and the Table I evidence; results tables; uncertainty budget per result:
  | Entry | Static torque | Current rise | Basis |
  |---|---|---|---|
  | 3D end flux | dominant, sign − (model low) | sign + (model fast) | not quantified in 2D; M5d hook checks it |
  | Eddy currents | 0 (steady state) | sign + | out of scope (§2.3) |
  | R 3.09 vs 3.12 Ω | — | from script | computed |
  | Voltage overshoot (Table II) | — | from script | computed |
  | Js tail | from script | from script | computed |
  | Mesh | from script | — | computed |
  | Table rounding (2 decimals) | ±0.005/3.22 | ±0.005/i | arithmetic |
- Core spec: §10 TEAM 24 item removed; §11 entry (2026-10-04) records decisions 1–4 and the result; §2.3/§8.2 wording unchanged. `CLAUDE.md` references to the feasibility doc point to the results doc; M5b marked done.
- `docs/m5-roadmap.md`: M5d scope gains "apply the end-effect hook to TEAM 24 as an independent check".

## Out of scope
Hall-probe B_y (Table VI: a point 7.7 mm inside the pole end, a 3D quantity); transient eddy-current modelling (sub-project #4); end-effect correction (M5d).

## Done
Slow test green locally on Windows (CI runs only the fast suite, so Linux coverage of the slow test waits for M5e's "all suites on CI" item); fast suite unchanged and green; results doc with error and uncertainty; spec §10 item closed in §11.
