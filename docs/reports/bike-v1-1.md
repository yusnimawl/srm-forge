# Bike v1, part 1: speed checks

Merged MERGE_DATE, PR #47 (same PR as part 0). Versions after the merge: srmapp 0.12.0, srmweb 0.12.2 (see `bike-v1-0.md`).
Plan `docs/superpowers/plans/2026-11-27-bike-v1-gates.md` (D10, D11; Tasks 11 and 12). Detailed results `docs/bike-v1-gates-results.md`, sources `docs/r5-sources.md` sections 10 and 11.

## Goal

Stop the search from passing a rotor shaft that bends or a bearing that cannot turn at the top speed. Done when: both checks sit in `hard_limits`, reject in search and in a case, and state their assumptions in the notes.

## What shipped

- Bending in `srmapp.limits`: first bending speed by Dunkerley, 1/w^2 = 1/w_r^2 + 1/w_s^2. The rotor laminations sit at mid-span. The shaft is uniform. Supports are rigid and simple. The limit is 1.3 x top speed (`BENDING_MARGIN`).
- Span: `BearingSetup.span_m`, or the stack plus both end windings plus 2 x `SPAN_ALLOWANCE` (15 mm). The allowance is a placeholder and the note says so. A `span_m` shorter than the stack fails the check.
- Bearing speed in `srmapp.limits`: 1.2 x top speed against the catalogue limiting speed x 0.81 (`DB_PRELOAD_A`, SKF Table 39, preload A). It never returns `not_run`.
- `BearingSetup.candidate` and `.lubrication` (grease or oil_air, default grease). With no candidate the check uses the lowest of the three candidate limits, 25 920 r/min on grease. That passes a top speed of 21 600 r/min or less.
- The note names the lubrication, the catalogue speed and the factor.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Bearing check at the 20 000 r/min target | passes on every candidate (1.2 x 20 000 = 24 000 r/min, under 25 920) | `docs/bike-v1-gates-results.md` |
| Bearing check at ratio 15 (19 894 r/min) | check speed 23 873 r/min, pass | same |
| Bearing limits, grease, catalogue x 0.81 | 34 830, 25 920 and 30 780 r/min for the three candidates | same |
| Bending, stage-1 passing designs below 1.3 at ratio 8 | 6/4 0 of 1, 8/6 2 of 16, 12/8 0 of 11, 24/16 0 of 22 | probes 2026-11-27 (Rayleigh model, not committed) |
| Bending, same at ratio 15 | 6/4 4 of 9, 8/6 9 of 27, 12/8 2 of 20, 24/16 0 of 36 | same |
| Bending rejects in the committed gate counts (250 samples) | ratio 12: 2 in 12/8. Ratio 15: 6 in 12/8 | `bike_gates_counts.json` |

Against the 10 to 15 % target:
- Bending: the supports are rigid, so the speed reads high (unsafe sign). The size has no cited value, because no bearing stiffness was found. The Dunkerley sum, the missing stack stiffness and the mid-span lump read low (safe). The 1.3 margin is not tied to a measured error, and no measured bending speed of a small SRM rotor was found. The figure is not validated.
- Bearing speed: this is a pass or fail on a catalogue number, not an accuracy claim.

## Decisions

- 2026-11-27, owner: bearing speed blocks, at the catalogue limit x the preload factor.
- 2026-11-28, owner: the factor is 0.81 (SKF preload A).
- 2026-11-28, owner: no further bearing questions; the lamination design comes first.
- 2026-11-28, builder: the candidate is a field. No rule picks the smallest bore that fits the shaft (the shaft diameter is sampled, and a journal can step down).
- 2026-11-28, builder: a note for each limit states its assumptions whatever the status (the caveat field).
- 2026-11-28, builder: a `span_m` shorter than the stack gives a bending fail (unsafe side).

## Open after this step

- `span_m` from the end-cap drawing: 15 mm per end may be short for a double-bearing set at each end. Tracker.
- Bearing radial stiffness in the bending check (no cited value): the rigid supports read the speed high. Tracker.
- A measured bending speed of a small SRM rotor, to tie the 1.3 margin to an error.
- FE stress and critical speed (Bike motor v1, part 8).

## Evidence

- PR #47. Fast tests as in `bike-v1-0.md`. CI: fast suite run 46145531326 and slow suite run 46145550295 green on PR #47 (slow app part 11 passed in 4 h 10 min 43 s).
- Each task had one review, and the final fix round fixed the bearing note and the span rule.
