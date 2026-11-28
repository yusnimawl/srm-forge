# Bike v1, part 0: gates and ranking

Merged MERGE_DATE, PR #47. Versions after the merge: srmapp 0.12.0, srmweb 0.12.2 (srmcore stays 0.8.0, `web/` stays 0.12.0, schema regenerated, no UI change).
Plan `docs/superpowers/plans/2026-11-27-bike-v1-gates.md` (D1 to D14). Detailed results `docs/bike-v1-gates-results.md`.

## Goal

Make the bike search enforce hard limits, rate designs at the shaft, and name one design. Done when: the limits reject designs in search and in a case, ratings are at shaft torque, and the search gives a recommendation or says why it gives none.

## What shipped

- `srmapp.limits`: `Limit(name, status, value, limit, note, caveat)` with status pass, fail or not_run. `hard_limits` holds rotor stress (safety factor at least 1.5 at 1.2 x top speed), iron frequency (at most 2780 Hz, the end of the iron-loss factor curve), bending and bearing speed (part 1). `gap_limit` runs after a rating. Rotor yoke floor is now 0.55.
- Search rejects any `fail`, and `not_run` for rotor stress and bending. A case evaluation marks a `fail` infeasible and notes each `not_run`. `SearchResult.limit_rejected` counts the rejections.
- The generator drops a pole set above the frequency cap before sampling (`dropped_pole_sets`, 16/12 added to the set list). `Requirements.max_length_m` drops long samples and fails a case.
- Honest thermal errors: only `MissingLossData` and `MissingCoolingData` are refusals. Any other thermal failure makes the design infeasible. `run_search` stops after 3 equal failures (`SearchResult.stopped`).
- Shaft-torque ratings: `load_at` asks a stroke that also covers (iron loss x iron factor + windage and friction) / omega. Secant steps to 1e-3, at most 6 strokes. `peak_power_w`, `peak_torque_nm` and `continuous_power_w` are at the shaft.
- Ripple-limited winding current (`turns.ripple_limited`): with `switching_frequency_hz` set, each winding current is lowered so I + dI/2 stays at or below `phase_current_a`. Hard chopping, zero back-EMF, highest bus voltage.
- Single pulse first in density mode: `Envelope.torque_single_pulse`, `ScanPoint.single_pulse`.
- Shortlist order: likely designs first by `BOUND_SHARE` 0.699, then lightest, round-robin over pole sets. It drops nothing.
- Objective: `recommended()` is feasible, rated, lightest first. Evaluations carry nominal kW/kg and `nominal_check`. `recommendation` is None when `margin_sensitive()` finds a lighter design that holds only the nominal check.
- Gap closure limit: at most 0.5 x air gap, centrifugal part only, and only when the rotor is not hotter than the bore.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Rating at shaft torque, 8/6 screening, rated set | continuous and peak 10.1 to 11.8 % lower at 6 speeds | LattePanda, `bike_gates_rating_screening*.json` |
| Same, nominal set | 2.8 to 3.7 % lower | same |
| Envelope check | branch = (main - loss torque) x 0.999 at all 6 speeds | same |
| Rating time | 5141 s against 739 s (about 7x), 214 stroke entries, 174 solved | same |
| Case feasibility | infeasible: shaft top 2.7 to 2.9 N.m against 3.0 N.m asked | same |
| Frequency cap | 24/16 dropped at ratio 8, 12 and 15. 16/12 dropped at 12 and 15 (3182, 3978 Hz) | `bike_gates_counts.json`, 18 s |
| Rotor stress rejects (250 samples per ratio) | ratio 8: 4 in 16/12. Ratio 12: 3 in 12/8. Ratio 15: 5 in 12/8, 1 in 8/6 | same |
| `BOUND_SHARE` | shares 0.318 to 0.636 over 9 designs, x 1.1 = 0.699 | `bike_gates_bound_share.json`, 6491.5 s |
| Regulated current at 20 kHz, 420 V | 75.2 to 89.1 % of the 170 A device peak | same |
| Best density winding in those 9 scans | not single pulse, none feasible at margin 1.05 | same |
| `RATING_BUDGET_S` screening | 6426 s (5141 x 1.25) | `src/srmweb/cases.py` |

Against the 10 to 15 % target:
- Ripple: the claim is on the safe side. Hard chopping gives twice the soft-chopping ripple, and L takes the free-air end winding and the Lu gap. The lower map node costs about 1 to 2 % of current (estimate, not measured).
- Gap closure: tip growth reads up to 9 % low against the FE (unsafe sign). The thermal path raises it by 1 / (1 - 0.094). On bike designs the check is `not_run`, so it blocks nothing.
- Shaft rating: counting all iron loss as drag is the safe side. The 10.1 to 11.8 % drop is the iron factor 3.2 on a 2.7 to 2.8 N.m machine.
- Peak kW/kg is a band from rated to nominal. The cooling paths and a 30 s peak from warm have no measured check.

## Decisions

- 2026-11-27, planner: search is strict, a case is evaluated as given (D2).
- 2026-11-28: windage stays in the rated set and is counted once. Kiyota's "iron and other" leaves the mechanical loss out (Table III), so the iron factor holds no windage.
- 2026-11-28, owner: the ranking states the peak-rating gap as a band, and the cooling paths are checked on the winner.
- 2026-11-28, builder: accept the 10.1 to 11.8 % rated drop (the loss torque explains all of it, safe direction).
- 2026-11-28, builder: keep the 7x rating time and set the screening budget to measured x 1.25 (correctness first).
- 2026-11-28, builder: the gap check runs centrifugal-only only with the rotor at or below the bore temperature (the plan had the sign wrong).
- 2026-11-28, builder: ripple L uses image factor 1.0 and divides by 1 + `MEASURED_LU_GAP`.

## Open after this step

- Rating speed-up (about 7x): reuse strokes within `DRAG_TOL`, start the shaft top from the previous speed. Tracker.
- `RATING_BUDGET_S` full 14189 s and reference 56747 s are scaled from the screening ratio, not measured. Tracker.
- 10JNEX900 expansion coefficient: the gap check is `not_run` on bike designs. Tracker (lamination data row).
- Mutual coupling is not modelled.
- Inverter and chopping mode are not chosen. Hard chopping is assumed.
- Efficiency map still counts EM power as output.
- FE stress sweep for 12-pole rotors at 4 phases (16/12 samples fail on pole arc).
- 10JNEX900 ring test above 2.78 kHz would lift the frequency cap.
- Cooling-path check and a 30 s peak from warm: confirm step on the winner.

## Evidence

- PR #47. Local fast tests: app, evaluate (60), web (327), vitest (343) passed. CI: fast suite run 46145531326 and slow suite run 46145550295 green on PR #47 (slow app part 11 passed in 4 h 10 min 43 s).
- Built from the plan, one implementer and one review per task, a final whole-branch review and fix rounds.
