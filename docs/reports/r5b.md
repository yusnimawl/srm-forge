# R5b: Cooling options, thermal network and ratings

Merged 2026-11-09, PR #24. Versions after the merge: srmcore 0.7.0 (unchanged).
Spec `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md`. Plan `docs/superpowers/plans/2026-11-09-r5b-cooling-ratings.md`. Detailed results `docs/r5-thermal-results.md`, sources `docs/r5-sources.md` sections 6 to 8.

## Goal

Add cooling options, a thermal network around the R5a solver, and a continuous and peak rating per speed. Gate V3 checks the winding conductivity model against Marquez-Fernandez 2018.

## What shipped

- `srmcore.thermal.correlations` (fluids, Gnielinski duct h, Faiz air-gap h, Churchill-Chu natural h) and `homogenise` (Hashin-Shtrikman lower bound, Milton).
- `srmapp.cooling` (`CoolingSetup`, `coefficients`, the unfavourable-end budget rows), `thermal_network`, `thermal_load` and `thermal` (`rate`, `rate_speed`, `Rating`).
- Cited defaults only. Refused instead of guessed: oil end spray, shaft oil, oil in the slot, a laminar jacket.
- No web route or tab yet.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| V3, Milton at fill 0.37 | 2.430 against printed 2.41 W/(m K) (+0.8 %) | `srmcore.thermal.homogenise` |
| V3, Milton at fill 0.47 | 3.439 against printed 3.11 W/(m K) (+10.6 %): not reproduced | same |
| First 8/6 rating, nominal continuous | 3.23 N·m at 2000 r/min, 3.16 N·m at 6000 r/min | `screening` test fixture, 160 degC limit |
| First 8/6 rating, rated (every row unfavourable) | 2.30 and 2.23 N·m | same |
| Largest budget share at 2000 r/min | liner row, 16.9 K of hot-spot rise | same |
| Fast suite | 1620 passed | PR #24 |

## Decisions

- 2026-11-09, builder: a cooling option with no cited band is refused, not given a guessed h.
- 2026-11-09, builder: the liner takes its plain conductivity over the full band, no coil contact assumed (errs hot).
- 2026-11-09, builder: iron has zero heat capacity (no cited specific heat), which makes the peak transient the conservative side.
- 2026-11-09, builder: the peak starts from the required continuous torque (read literally, peak would equal continuous). The owner confirmed this on 2026-11-10.
- 2026-11-10, owner: end spray runs on Shell Diala S4 ZX-I. Its cp comes from Cragoe 1929 (PR #25).

## Open after this step

- V3 is not reproduced. No cited xi exists for fills other than 0.37 (follow-up PR #27 put the error in the `cross_wire` band).
- A re-rate with new cooling needs new strokes (the R6 reuse promise is open).
- The default cooling values are flagged placeholders (water jacket, 9 L/min, 65 degC).
- Gates V0, V2, V4, V5 wait for R5e.

## Evidence

CI green on Windows and Linux plus web. Reviews moved three choices to the safe side (liner conductivity, peak hot spot as the transient maximum, a real 8/6 map in the slow test). The first rating is a test fixture, not a validation.
