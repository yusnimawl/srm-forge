# Bike gates: measurement results

Machine: LattePanda (i5-1340P), 2026-11-28. Torques are in N.m at the shaft.

## Rating at shaft torque, 8/6 screening case

Both runs use `examples/rating_timing.py --preset screening` (the rated 8/6 case of `tests/app/test_thermal_check.py`) with a fresh cache. Main is srmapp 0.11.0 (commit 590a9d8). The branch rates at shaft torque: the loss torque (iron loss x iron factor + windage and friction) / omega comes off the torque the stroke must give. The records are `docs/validation/bike_gates_rating_screening.json` (branch) and `docs/validation/bike_gates_rating_screening_main.json` (main). The main record is from a second main run on the cache of the first, so it holds the per-speed numbers; its time is not a measurement.

Rated set (every row unfavourable, torque factor 1.10, iron factor 3.20). Every change is a drop.

| rpm | Main cont. | Branch cont. | Change | Main peak | Branch peak | Change | Loss torque at envelope |
|---|---|---|---|---|---|---|---|
| 1000 | 3.110 | 2.795 | -10.1 % | 3.110 | 2.795 | -10.1 % | 0.296 |
| 2000 | 3.105 | 2.783 | -10.4 % | 3.105 | 2.783 | -10.4 % | 0.319 |
| 3000 | 3.094 | 2.753 | -11.0 % | 3.094 | 2.753 | -11.0 % | 0.339 |
| 4000 | 3.083 | 2.718 | -11.8 % | 3.083 | 2.718 | -11.8 % | 0.337 |
| 5000 | 3.067 | 2.716 | -11.4 % | 3.067 | 2.716 | -11.4 % | 0.348 |
| 6000 | 3.048 | 2.701 | -11.4 % | 3.048 | 2.701 | -11.4 % | 0.344 |

The loss torque is taken from the branch stroke at the EM envelope. At all 6 speeds the branch envelope torque equals (main envelope torque - loss torque) x (1 - 0.001), the stroke tolerance. On main the continuous and peak torques equal the envelope torque at every speed. On the branch they equal it at 2000, 3000, 5000 and 6000 rpm, and sit 0.6 to 1.0 % below it at 1000 and 4000 rpm (rated), so the drop there is slightly larger than the loss torque.

The rated drop is 10.1 to 11.8 %, over 10 % at all 6 speeds. The loss torque explains all of it, and the rated set's iron factor of 3.2 (the Kiyota measured-over-model factor) makes it large on this 2.4 N.m 8/6. The drop is accepted.

Nominal set (no row unfavourable). Every change is a drop of 2.8 to 3.7 %.

| rpm | Main cont. | Branch cont. | Change | Main peak | Branch peak | Change | Loss torque at envelope |
|---|---|---|---|---|---|---|---|
| 1000 | 3.421 | 3.325 | -2.8 % | 3.421 | 3.325 | -2.8 % | 0.093 |
| 2000 | 3.416 | 3.296 | -3.5 % | 3.416 | 3.296 | -3.5 % | 0.100 |
| 3000 | 3.404 | 3.294 | -3.2 % | 3.404 | 3.294 | -3.2 % | 0.107 |
| 4000 | 3.391 | 3.265 | -3.7 % | 3.391 | 3.265 | -3.7 % | 0.106 |
| 5000 | 3.373 | 3.260 | -3.4 % | 3.373 | 3.260 | -3.4 % | 0.110 |
| 6000 | 3.353 | 3.240 | -3.3 % | 3.353 | 3.240 | -3.3 % | 0.109 |

## Time

| | Rating time | Total | Strokes solved |
|---|---|---|---|
| Main (srmapp 0.11.0) | 738.8 s | 1043.3 s | 24 (second run) |
| Branch | 5140.8 s | 5435.4 s | 214 |

The branch takes 214 strokes and main 24. Main's 8/6 is EM-limited, so it needs 2 strokes per speed and set (the required torque and the top). On the branch, finding the shaft-torque top takes a secant search, and each step runs a drag loop of 2 to 3 strokes.

`RATING_BUDGET_S` in `src/srmweb/cases.py` was 1063 s (screening), 2039 s (full) and 8155 s (reference). Screening is now 6426 s, the measured 5141 s x 1.25. Full is 14189 s and reference 56747 s: the old values x (5141 / 738.8), rounded to the second. Full and reference are scaled, not measured.

## Gate counts

Command: `PYTHONPATH=src:tests python examples/gate_counts.py --json docs/validation/bike_gates_counts.json` (18 s, no maps). 250 screening candidates per ratio, seed 0, split over the pole sets that the frequency limit keeps. A design counts once under each limit it fails.

Ratio 8. Dropped pole sets: 24/16 (stator electrical frequency 2829 Hz at top speed, above 2780 Hz (end of the iron-loss data)).

| Pole set | Sampled | Stage 1 pass | rotor_stress | Limit-rejected |
|---|---|---|---|---|
| 12/8 | 62 | 7 | 0 | 0 |
| 16/12 | 62 | 13 | 4 | 4 |
| 6/4 | 63 | 4 | 0 | 0 |
| 8/6 | 63 | 8 | 0 | 0 |

Ratio 12. Dropped pole sets: 16/12 (stator electrical frequency 3182 Hz at top speed, above 2780 Hz (end of the iron-loss data)); 24/16 (stator electrical frequency 4243 Hz at top speed, above 2780 Hz (end of the iron-loss data)).

| Pole set | Sampled | Stage 1 pass | bending | rotor_stress | Limit-rejected |
|---|---|---|---|---|---|
| 12/8 | 83 | 32 | 2 | 3 | 5 |
| 6/4 | 84 | 5 | 0 | 0 | 0 |
| 8/6 | 83 | 28 | 0 | 0 | 0 |

Ratio 15. Dropped pole sets: 16/12 (stator electrical frequency 3978 Hz at top speed, above 2780 Hz (end of the iron-loss data)); 24/16 (stator electrical frequency 5304 Hz at top speed, above 2780 Hz (end of the iron-loss data)).

| Pole set | Sampled | Stage 1 pass | bending | rotor_stress | Limit-rejected |
|---|---|---|---|---|---|
| 12/8 | 83 | 39 | 6 | 5 | 11 |
| 6/4 | 84 | 12 | 0 | 0 | 0 |
| 8/6 | 83 | 39 | 0 | 1 | 1 |
