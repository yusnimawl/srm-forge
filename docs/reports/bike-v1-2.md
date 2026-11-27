# Bike v1, part 2: continuous conduction in the drive model

Merged 2026-11-27, PR #44. Versions after the merge: srmapp 0.10.0, srmweb 0.12.1 (`web/` stays 0.12.0, srmcore stays 0.8.0).
Plan `docs/superpowers/plans/2026-11-26-continuous-conduction.md`. Detailed results `docs/r3-loss-results.md` (Kiyota section) and `docs/winding-scan-profile.md`.

## Goal

The drive envelope rejected every stroke whose phase flux did not die away before the next turn-on, so it under-predicted high-speed power. Done when: continuous-conduction strokes are in the envelope, the Kiyota (b), 59 kW and 99 kW points have strokes, every single-pulse result is unchanged, merged with CI green.

## What shipped

- `srmapp.drive.envelope`: `_run` takes a start flux per stroke. `_simulate` is unchanged. A stroke that `_simulate` rejects is solved as its periodic steady state (Illinois regula falsi on the start flux, `PERIODIC_TOL` 1e-6, `PERIODIC_MAX_ITER` 60).
- A periodic stroke is accepted only when it converged and its current stays within the limit under full negative voltage.
- `envelope`, `min_copper_stroke`, `fixed_stroke` and the waveforms use it. `StrokeTrace.psi_on` holds the flux at turn-on (0 for a single pulse).
- An evaluation note names the speeds where the chosen winding needs continuous conduction.
- `examples/kiyota_losses_check.py` reports the conduction of each stroke.
- `SCAN_BUDGET_S` is 454.1 s for auto and 8.0 s for fixed.
- The fast CI job runs in three parts: scan, app and rest.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Kiyota (b), 113 N·m at 8700 r/min | stroke found (none before); RMS 136.7 A vs 130 A measured (+5.1 %); torque 117.7 N·m (+4.1 %); peak 206.7 A vs 205 A | LattePanda, `full`, `docs/validation/kiyota_cc_16p3.json` |
| Kiyota 59 and 99 kW at 13 900 r/min | strokes found at both yokes (none before) | `kiyota_cc_16p3.json`, `kiyota_cc_15p5.json` |
| Single-pulse rows, Kiyota | equal to the 2026-11-18 run in every field | `kiyota_single_pulse_*.json` |
| Plan line: (b) current stroke within 0.5 % of 130 A | fail: 136.7 A at 16.3 mm, 117.4 A at 15.5 mm (cause: 8-level current-limit grid, 37.5 A steps) | `docs/r3-loss-results.md` |
| Measured over model iron loss at continuous points | 9.3 to 12.8 (rated factor `K_IRON_HI` is 3.2 to 7.0) | Kiyota JSONs |
| 8/6, fixed 242 turns: single-pulse speeds | equal to main bit for bit; 6000 r/min torque 1.78 to 9.03 N·m | `docs/validation/cc86_8_6_density.json` |
| 8/6, auto winding (density mode) | 242 to 500 turns (the scan limit) | `cc86_8_6_density.json` |
| Winding scan, density auto, 8 workers | 57.2 s to 363.3 s (wire auto 3.8 s to 5.8 s) | `docs/validation/scan_timing_cc.json` |
| Fast CI, longest part | 34.5 min of 60 | run 45893584508 |

## Decisions

- 2026-11-26, builder: the periodic solve runs only on strokes the single pulse rejects, so single-pulse numbers stay bit for bit.
- 2026-11-27, builder: the failed (b) current-match line is recorded, not fixed; the current-limit grid is its own tracker item.
- 2026-11-27, builder: the fast CI job is split instead of its 60 min limit raised.
- 2026-11-27, owner: merge, and make density mode prefer windings that work in single pulse until mutual coupling is measured (a follow-up change).

## Open after this step

- The iron-loss factor at high power (measured 9.3 to 12.8 x the model). Tracker item, before the bike search.
- The current-limit grid for continuous strokes. Tracker item, before the bike search.
- Density mode prefers single-pulse windings (owner, 2026-11-27). In step 0 of Bike motor v1.
- Mutual coupling under continuous conduction. Bike motor v1, the confirm step.
- The rated-evaluation time budget, not re-measured. Tracker item, Later.

## Evidence

- PR #44: fast CI green, runs 45881424969, 45889108882 and 45893584508.
- Slow suite green 4/4 on the branch: run 45881425276 (web 40 min, validation 79 min, rest 106 min, app 120 min).
- Built from the plan, one implementer and one review per task (Opus reviewers), then a final whole-branch review on Opus, one fix wave and its scoped re-review.
