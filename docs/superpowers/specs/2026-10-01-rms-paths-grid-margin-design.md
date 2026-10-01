# Small Cycle: RMS Current Density, Parallel Paths, On/Off Grid, Margin — Design Spec

Addendum to `2026-10-01-v0a2-turns-after-map-design.md` (items §10.1, §10.2 and decisions §10 (a), (b)). Owner-approved 2026-10-01. Correctness first; run time is not a constraint.

## 1. Problem

Four changes that alter which designs count as feasible, done before M5:

1. `j_limit` applies to the peak current, but cooling sees the RMS current (roughly half the peak in an SRM).
2. Poles of a phase are always in series; parallel paths give other current/turns combinations for the same wire.
3. The 40 x 40 on/off grid moved the ratios by up to +3.3 % against 80 x 80 (spec v0a-2 §10).
4. Feasibility is `worst ratio >= 1.0` in stage 2; the owner wants a margin setting, default 1.05.

## 2. RMS current density

- `envelope(..., rms_limit: float | None = None)`, in phase amperes. `_simulate` already returns ∫i² dθ per (on, off) pair. Phase RMS current over one rotor pole pitch: I_rms = √(∫i² dθ / pitch). At each speed, a stroke is valid only if it also satisfies I_rms ≤ `rms_limit` (with the existing relative tolerance 1e-9); the best valid stroke is picked as before.
- `Envelope` gains `i_rms: np.ndarray` (per speed, of the chosen stroke; 0 where no stroke is valid).
- The current density limit `j_limit` applies to the conductor RMS density: `rms_limit = j_limit · paths · copper_area` (copper_area is one turn, all strands; the phase current splits over the paths). This holds in both modes. In density mode `j_limit` defaults to `j_peak`, so it binds only when set lower.
- Peak current density is bounded by `j_peak_max` (§4). Peak phase current is bounded by `phase_current_a` as before.
- Known limit: the drive meets the RMS limit only by changing the turn-on and turn-off angles; it does not lower the hysteresis current. A current-limit sweep comes with the efficiency-map cycle. Torque under a binding RMS limit may be underestimated.

## 3. Parallel paths

- `Winding.paths: int` (a), from the divisors of the poles per phase (`n_stator_poles / n_phases`), all tried.
- A phase with a equal parallel paths of N turns per pole, phase current I: coil current I/a, phase flux linkage ψ_series/a. On the map this equals N/a turns in series: the scan uses `rescale_turns(result, N / (a · N_ref))`. Equal current sharing is assumed (as `srmcore.physics.winding` assumes).
- Resistance R = R_series(N, copper_area) / a². Copper mass unchanged.
- `Winding.current` stays the peak phase current. `Winding.current_density` = current / (paths · copper_area).
- The `Design` has no paths field; the chosen design keeps `turns_per_pole = N` and the paths are recorded in `Evaluation.winding.paths`. Key numbers are computed on the map rescaled by N/(a·N_ref), so La, Lu and ψ_max are phase values.
- Wire mode: for each wire, path count and turn count, as many parallel strands as fit (unchanged rule), peak density ≤ `j_peak_max`. Choice: lowest resistance, ties to fewer turns, then fewer paths.
- Density mode: turn counts 1..`max_turns` for each path count, coil current `j_peak · copper_area`, phase current a times that, left out above `phase_current_a`. Choice: most turns, ties to fewer paths.

## 4. Settings

`SearchSettings`:

- `margin: float = 1.05` (was 1.0). Stage 1 already uses it on the torque bound. Stage 2: a scan point is feasible when min(torque ratio, power ratio) ≥ `margin`. `choose_turns` takes `margin`; `ScanPoint.feasible` becomes a field set by the scan.
- `j_peak_max: float | None = None` — peak conductor current density cap in wire mode, A/m²; None means 2 · `j_limit`. It bounds the windings scanned and thus the map current range (`max_mmf`). Stage 1 and stage 2 receive the resolved value.

## 5. On/off grid

`N_ON = N_OFF = 80`, dense (decision §10 (a)). Measured: 0.14 s per envelope at 6 speeds against 0.06 s at 40 x 40. No coarse-to-fine search: the on/off resolution is already capped by `N_THETA = 181` (about 99 index positions per range), and a dense grid needs no extra validation.

## 6. Evaluation outputs

- `ScanPoint`: add `i_rms` and `j_rms` (worst over base..max speed), `feasible` field.
- `Evaluation`: add `i_rms_a` and `j_rms` (worst over the full speed grid of the chosen winding; NaN without a winding). `winding.paths` reported through `winding`.
- Note in `Evaluation.error` (status "ok") when no scanned winding is feasible in wire mode and `j_peak_max` left out windings that fit the slot (`TurnsChoice.capped`): a higher cap might allow a feasible winding. (A chosen winding sits exactly at the cap only by chance, since strand counts are whole numbers, so that case is not the trigger.)

## 7. Testing

- Envelope: `rms_limit` above the unconstrained I_rms changes nothing; a binding `rms_limit` lowers torque at low speed and the chosen stroke's I_rms ≤ limit; `i_rms` matches √(∫i²/pitch) on a constant-current stroke.
- Paths: an evaluation with a = 2 at N turns gives the same envelope as N/2 turns in series with R/4 (same phase current); invalid path counts are never generated (divisors only); R and coil current scale as stated.
- Wire mode: windings with peak density above `j_peak_max` are left out; windings with peak density above `j_limit` but RMS within it are kept; the cap note appears on an infeasible, capped result.
- Margin: a winding with worst ratio in [1.0, 1.05) is infeasible at the default and feasible at `margin=1.0`.
- Existing tests updated for the new defaults.

## 8. Accuracy re-run

After the change, re-run `examples/v0_angle_check.py` with the new defaults. The on/off grid variant compares 80 x 80 against a 160 x 160 reference at `N_THETA = 361`; the limit is 2 % on each ratio (v0a-2 §5). Record the results in `docs/m4-handoff.md` next to the v0a-2 results. Fix the deferred minor that the script stops on a candidate with no winding (skip it with a printed line).

## 9. Dropped

- Coarse-to-fine on/off search (not needed, §5).
- Lowering the hysteresis current to meet the RMS limit (efficiency-map cycle).
- A paths field on `Design` (the app records it in the winding; `srmcore` already supports paths in the FEM winding but the map is path-independent).
