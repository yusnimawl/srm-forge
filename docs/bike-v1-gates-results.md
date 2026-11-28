# Bike gates: measurement results

Machine: LattePanda (i5-1340P), 2026-11-28. Torques are in N.m at the shaft.

## Rating at shaft torque, 8/6 screening case

Main is srmapp 0.11.0 (commit 590a9d8). The branch rates at shaft torque: the loss torque (iron loss x iron factor + windage and friction) / omega comes off the torque the stroke must give. The case is the rated 8/6 of `tests/app/test_thermal_check.py`, run with `examples/rating_timing.py --preset screening`.

Records:
- Branch: `docs/validation/bike_gates_rating_screening.json`, fresh cache.
- Main time: `docs/validation/bike_gates_rating_screening_main_timing.json`, fresh cache, map built (rating 738.8 s, total 1043.3 s). It has no per-speed numbers.
- Main per-speed numbers: `docs/validation/bike_gates_rating_screening_main.json`, a second main run on the cache of the first. Its time (134 s) is not a measurement. Where the two runs overlap, the strokes of the branch fresh run equal the cached main strokes to every digit.

The branch case is thermally infeasible. No winding holds the rated hot-spot limit, and 4 windings were checked. The case asks for 3.0 N.m at the shaft, and the shaft top is 2.7 to 2.9 N.m. That is physical: the loss torque comes off the EM envelope. Main holds the case. The branch strokes 0 to 52 are those failed checks and the nominal check. The timing therefore covers the full evaluate path, the path a web evaluation runs. That is why the budget is kept.

Rated set (every row unfavourable, torque factor 1.10, iron factor 3.20). Every change is a drop.

| rpm | Main cont. | Branch cont. | Change | Main peak | Branch peak | Change | Loss torque at envelope |
|---|---|---|---|---|---|---|---|
| 1000 | 3.110 | 2.795 | -10.1 % | 3.110 | 2.795 | -10.1 % | 0.296 |
| 2000 | 3.105 | 2.783 | -10.4 % | 3.105 | 2.783 | -10.4 % | 0.319 |
| 3000 | 3.094 | 2.753 | -11.0 % | 3.094 | 2.753 | -11.0 % | 0.339 |
| 4000 | 3.083 | 2.718 | -11.8 % | 3.083 | 2.718 | -11.8 % | 0.337 |
| 5000 | 3.067 | 2.716 | -11.4 % | 3.067 | 2.716 | -11.4 % | 0.348 |
| 6000 | 3.048 | 2.701 | -11.4 % | 3.048 | 2.701 | -11.4 % | 0.344 |

The loss torque column is the shaft-side loss torque (iron loss x iron factor + windage and friction, / omega, no torque factor) of the branch stroke at the EM envelope. At all 6 speeds in both sets the branch envelope torque equals (main envelope torque - loss torque) x (1 - 0.001), the stroke tolerance.

On main the continuous and peak torques equal the envelope torque at every speed. On the branch they do so except at 4 points: rated 1000 and 4000 rpm, and nominal 2000 and 4000 rpm. They sit 0.5 to 0.9 % below the envelope there. At these points the stroke at the shaft top carries more iron loss than the stroke at the EM top. It then needs more EM torque than the envelope gives and has no stroke. `rate_speed` brackets down and stays on the feasible side, within its 1 % stop rule. These brackets take about 123 of the 161 rating strokes, which is most of the 7x.

The rated drop is 10.1 to 11.8 %, over 10 % at all 6 speeds. The loss torque explains all of it, and the rated set's iron factor of 3.2 (the Kiyota measured-over-model factor) makes it large on this machine, where the rated shaft top is 2.7 to 2.8 N.m. The drop is accepted.

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

| | Rating time | Total | Stroke entries | Unique solved |
|---|---|---|---|---|
| Main (srmapp 0.11.0) | 738.8 s | 1043.3 s | 24 (second run) | |
| Branch | 5140.8 s | 5435.4 s | 214 | 174 |

The branch log has 214 stroke entries. The evaluate path makes a new context for each winding check and again for the rating, so a repeated stroke is logged again and read from the disk cache. 11 entries are None (no stroke, no solve). That leaves 174 unique solved strokes. Main's 24 are 12 check strokes and 12 rating strokes. Main's 8/6 is EM-limited, so a rating needs few strokes. On the branch, the shaft top and the points above need many more, mostly in the brackets named above.

`RATING_BUDGET_S` in `src/srmweb/cases.py` was 1063 s (screening), 2039 s (full) and 8155 s (reference). Screening is now 6426 s, the measured 5141 s x 1.25. Full is 14189 s and reference 56747 s: the old values x 5141 / 738.8, rounded to the second. Full and reference are scaled, not measured.

## Gate counts

Command: `PYTHONPATH=src:tests python examples/gate_counts.py --json docs/validation/bike_gates_counts.json` (18 s, no maps). 250 screening candidates per ratio, seed 0, split over the pole sets that the frequency limit keeps. A design counts once under each limit it fails.

Ratio 8. Dropped pole sets: 24/16: stator electrical frequency 2829 Hz at top speed, above 2780 Hz (end of the iron-loss data).

| Pole set | Sampled | Stage 1 pass | rotor_stress | Limit-rejected |
|---|---|---|---|---|
| 12/8 | 62 | 7 | 0 | 0 |
| 16/12 | 62 | 13 | 4 | 4 |
| 6/4 | 63 | 4 | 0 | 0 |
| 8/6 | 63 | 8 | 0 | 0 |

Ratio 12. Dropped pole sets: 16/12: stator electrical frequency 3182 Hz at top speed, above 2780 Hz (end of the iron-loss data); 24/16: stator electrical frequency 4243 Hz at top speed, above 2780 Hz (end of the iron-loss data).

| Pole set | Sampled | Stage 1 pass | bending | rotor_stress | Limit-rejected |
|---|---|---|---|---|---|
| 12/8 | 83 | 32 | 2 | 3 | 5 |
| 6/4 | 84 | 5 | 0 | 0 | 0 |
| 8/6 | 83 | 28 | 0 | 0 | 0 |

Ratio 15. Dropped pole sets: 16/12: stator electrical frequency 3978 Hz at top speed, above 2780 Hz (end of the iron-loss data); 24/16: stator electrical frequency 5304 Hz at top speed, above 2780 Hz (end of the iron-loss data).

| Pole set | Sampled | Stage 1 pass | bending | rotor_stress | Limit-rejected |
|---|---|---|---|---|---|
| 12/8 | 83 | 39 | 6 | 5 | 11 |
| 6/4 | 84 | 12 | 0 | 0 | 0 |
| 8/6 | 83 | 39 | 0 | 1 | 1 |
