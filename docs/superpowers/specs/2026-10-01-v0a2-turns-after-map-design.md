# v0a-2: Turns and Wire After the Map — Design Spec

Addendum to `2026-09-30-v0-walking-skeleton-design.md`. Owner-approved 2026-10-01. Correctness first; run time is not a constraint.

## 1. Problem

The v0a search found 0 of 6 designs feasible. Turns per pole were sampled independently of bus voltage and speed. The 2D magnetostatic map depends only on the coil MMF (N·i), so turns, wire and current can be chosen after the map without another FEM solve.

## 2. Exact rescale

The FEM map is built once per geometry at `REFERENCE_TURNS = N0`. For N turns, with k = N/N0:

- ψ_N(θ, i) = k · ψ_0(θ, k·i)
- T_N(θ, i) = T_0(θ, k·i)
- the map current axis becomes i_0 / k

This is exact for a uniform current density in the coil region (what the FEM models). It ignores the effect of conductor discretisation on the field, which the FEM does not model either. A slow test builds maps at N0 and 2·N0 (with I_max halved) and requires agreement after the rescale to solver tolerance.

## 3. Modes

Both modes use the same map and the same turns scan. They differ in what is fixed.

| | Wire mode (default) | Density mode |
|---|---|---|
| Fixed | wire list, phase current I, max slot fill | current density J (`j_peak`), fill factor 0.5 |
| Per N | parallel strands p = floor(fill·A_side / (N·a_out)) | conductor area fill·A_side / N |
| Constraint | I / (p·a_cu) ≤ j_limit, p ≥ 1 | i_peak(N) ≤ `phase_current_a` when set |
| Choice | smallest N meeting torque and power; then the wire with the lowest R | largest N meeting torque and power (lowest current) |

A_side is `coil_side_area` (one coil side). Each coil side holds N·p conductors.

### 3.1 Wire

A `Wire` is described by dimensions; the tool derives `a_cu` (copper area per conductor) and `a_out` (outer area, insulation included):

- `round`: bare Ø, insulated Ø
- `rectangular`: width × height, insulation thickness (corner radius ignored)
- `litz` / `multistrand`: strand Ø × strand count, bundle outer Ø

Strand Ø is kept so an AC-loss model can be added later.

### 3.2 Requirements and settings

- `Requirements.wires: list[Wire]`, `phase_current_a`, `max_slot_fill` (default 0.6, outer-area basis). Wire mode is active when `wires` is non-empty.
- `phase_current_a` is the inverter's peak phase current: required in wire mode, an optional cap in density mode.
- `SearchSettings.j_limit` (A/m², cooling limit). The existing `j_peak` stays the density-mode J.

### 3.3 Map current range

The map covers MMF up to the largest N·I over the allowed windings in wire mode (at most `j_limit · fill · A_side · max(a_cu / a_out)`), and `j_peak · 0.5 · A_side` in density mode. No N, wire or current combination allowed by the constraints exceeds it. The map's I_max is that MMF divided by N0.

### 3.4 Turns scan

Every integer N from 1 up to the largest N that fits (p ≥ 1) is evaluated:

1. Derive p (wire mode) or the conductor area (density mode); skip N if it violates the constraint.
2. Rescale the tables by k = N/N0 and clip the current limit at I (wire mode) or i_peak(N) (density mode).
3. Run the drive envelope with R(N) and record the torque and power ratios.

The choice follows the table above. If no N is feasible, the N with the largest min(torque ratio, power ratio) is reported and the design is infeasible. The scan curve (N, p, ratios, R) is kept in the `Evaluation`.

R = ρ(T) · N · (Ns/m) · MLT / (p · a_cu), poles in series. Copper mass = Ns · N · p · a_cu · MLT · density.

## 4. Stage 1

- The torque bound uses the maximum MMF of §3.3, so it does not depend on turns.
- The mass limit uses iron mass only, which never drops a design wrongly. The full mass check runs after the wire is chosen.
- The generator drops turns from its sampled dimensions (9 → 8) and sets `turns_per_pole = N0`.

## 5. Stage-2 accuracy

- The generator uses the `full` mesh preset; `StageTwoGrid` defaults to the preset grid (30 × 20).
- `examples/v0_angle_check.py`: for one design per pole set, compares the envelope (torque and power at base and maximum speed) from 30 angles against 60 angles on the `full` mesh, and the drive discretisation (N_THETA 181 against 361, 40 × 40 against 80 × 80 on/off grid). Results are recorded in `docs/m4-handoff.md`. Differences above 2 % go to the owner before any default changes.

## 6. Evaluation outputs

Mode, wire (wire mode), N, p, R, J, peak phase current, copper mass, total mass, copper loss, ratios, the scan curve, and the design with `turns_per_pole = N`.

## 7. Testing

- Slow: rescale exactness (§2).
- Fast: wire areas per kind; the scan picks the smallest feasible N in wire mode and the largest in density mode; j_limit and the current cap are respected; the lowest-R wire wins; the stage-1 bound does not depend on turns; the generator no longer varies turns; the map MMF range covers every allowed combination.

## 8. Dropped

The speed-only levers in v0 spec §4 (half-pitch symmetry, skipping the zero-current column, optional L_inc) are dropped: none was implemented, and each risks changing results for time the owner does not care about.

## 9. Open

AC and litz losses (skin, proximity); parallel pole paths (scheduled, §10); rectangular corner radius; iron loss (scheduled, §10); mutual coupling; flux past alignment (conservative at high speed, unmeasured); stage-1 false-drop rate.

## 10. Accuracy check results and roadmap (owner-agreed 2026-10-01)

Results of §5 are in `docs/m4-handoff.md` ("v0a-2 stage-2 accuracy check"): 3 of 4 candidates feasible; angles, current count and N_THETA move the ratios by at most about 1 %; the 40 x 40 on/off grid moves them by +1.1 to +3.3 % (above 2 % on the 6/4). Decided 2026-10-01: (a) the on/off grid becomes at least 80 x 80; a coarse-to-fine search is allowed if it matches a dense reference within the accuracy-check tolerance; (b) a feasibility-margin setting, default 1.05, applied to the worst of the torque and power ratios; it reflects trust in the model and is revisited after M5. The Pareto plot shows each design's ratios.

Items taken from a comparison with JMAG-Express (`docs/jmag-express-srm-reference.md`). JMAG-Express is not followed where its method is weaker: it fixes one turn-on angle and width over the whole speed range (this project optimises them per speed), and its sizing derives turns from slot fill and wire area without reference to bus voltage or speed (the cause of the v0a 0-of-6 result).

Next, folded into the following work cycle (small, both change which designs count as feasible):
1. **RMS current and RMS current density.** The current-density limit in wire mode applies to the peak current; cooling sees the RMS current, which in an SRM is roughly half the peak. Compute I_rms from the envelope's ∫i² and apply `j_limit` to it; the peak current stays limited by `phase_current_a`. Report I_rms and J_rms per evaluation.
2. **Parallel pole paths.** Add the coil connection (series or parallel paths per phase) to the turns scan; `srmcore.physics.winding.phase_winding` already takes `parallel_paths`.

Own work cycles, in this order:
3. **Iron loss** and efficiency including it (core roadmap §1.3 item 2). The fixed iron mesh nodes give per-element flux waveforms.
4. **SRM efficiency maps** (speed vs torque) from the envelope by sweeping the current limit. JMAG-Express does not offer these for SRMs.
5. **Thermal model** for direct liquid cooling (core roadmap item 3). JMAG-Express has none for SRMs.

Later:
6. Inverter rating (VA per kW) as an output and a possible Pareto objective.
7. Correction factors (saturation, iron loss) to calibrate against test data, after M5.
8. Tapered teeth in the generator (geometry already supports taper; the generator fixes it at zero).
9. v0b web layer: keep every evaluation as a case (table, flags, comments, one-parameter sweeps, CSV/PDF export).
10. Flux-linkage LUT export in a Simulink/PSIM-ready format (CSV and .mat exist).
