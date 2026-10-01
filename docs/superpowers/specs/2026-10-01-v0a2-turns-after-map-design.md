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

The map covers MMF up to `j_limit · fill · A_side · max(a_cu / a_out)` over the wires in wire mode, and `j_peak · 0.5 · A_side` in density mode. No N, wire or current combination allowed by the constraints exceeds it. The map's I_max is that MMF divided by N0.

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

AC and litz losses (skin, proximity); parallel pole paths; rectangular corner radius; iron loss; mutual coupling; flux past alignment (conservative at high speed, unmeasured); stage-1 false-drop rate.
