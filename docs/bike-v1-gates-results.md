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

## Diagnosis tables (probes of 2026-11-27, LattePanda, not committed)

Bike requirement of the probes: 30 kW at the shaft, 12 kW continuous, 300 V, 170 A, stator OD at most 200 mm, 10JNEX900 stator and rotor, base speed max / 3, density mode. Top speed 150 km/h on a 0.60 m tyre is 1326 r/min at the wheel, so 10 610, 15 915 and 19 894 r/min at total ratios 8, 12 and 15. The branch changed the code after the probes, so these tables are the reason for each gate, not a test of the gates. The branch counts are in the table "Gate counts" above.

Rotor stress. 250 samples per ratio, 50 per pole set. Samples outside the validity box of the root model (`docs/r5-sources.md` section 5), at the old yoke floor 0.50 and the new floor 0.55:

| Pole set | Outside, floor 0.50 | Outside, floor 0.55 | In box with SF < 1.5, ratio 15 |
|---|---|---|---|
| 6/4 | 8 (yoke) | 0 | 0 of 50 |
| 8/6 | 3 (yoke) | 0 | 0 of 50 |
| 12/8 | 6 (3 yoke, 3 free ring span) | 5 (free ring span) | 0 of 45 |
| 24/16 | 2 (yoke) | 0 | 21 of 50 |
| 16/12 (q = 4) | 33 (32 pole arc) | 32 (pole arc) | 2 of 18 |

Top stator electrical frequency (N_r x top speed / 60). The cap is 2780 Hz, the last point of the Kiyota iron-loss factor curve:

| Pole set | Ratio 8 | Ratio 12 | Ratio 15 |
|---|---|---|---|
| 6/4 | 0.71 kHz | 1.06 kHz | 1.33 kHz |
| 8/6 | 1.06 kHz | 1.59 kHz | 1.99 kHz |
| 12/8 | 1.41 kHz | 2.12 kHz | 2.65 kHz |
| 16/12 | 2.12 kHz | 3.18 kHz | 3.98 kHz |
| 24/16 | 2.83 kHz | 4.24 kHz | 5.31 kHz |

Stage-1 torque bound against the drive torque at 50 r/min at the map top (share = drive over bound):

| Map | Ampere-turns | Drive torque | Bound | Share |
|---|---|---|---|---|
| 8/6 M19 screening | 600 | 5.38 N.m | 14.07 N.m | 0.38 |
| 8/6 M19 screening | 3258 | 42.19 N.m | 76.42 N.m | 0.55 |
| Kiyota 18/12 full | 6000 | 288.5 N.m | 511.2 N.m | 0.56 |

Current ripple. Lowest L_inc over the angles at the top current, against Lu (secant, low current):

| Map | Lu | Lowest L_inc at the top current | Where |
|---|---|---|---|
| 8/6 screening, 163 A at 20 turns | 0.413 mH | 0.096 mH | 0.97 of the pitch from unaligned |
| Kiyota 18/12, 300 A | 1.023 mH | 0.243 mH | aligned |
| 8/6 screening, 30 A at 20 turns | 0.412 mH | 0.416 mH | unaligned (no saturation) |

First bending (probe model: laminations at mid-span plus 17/35 of the shaft mass, Rayleigh; the code uses the Dunkerley bound, which reads a little lower). Stage-1 passing designs:

| Pole set | Ratio 8, below 1.3 | Ratio 15, below 1.3 | Ratio 15, lowest |
|---|---|---|---|
| 6/4 | 0 of 1 | 4 of 9 | 0.68 |
| 8/6 | 2 of 16 | 9 of 27 | 0.63 |
| 12/8 | 0 of 11 | 2 of 20 | 1.05 |
| 24/16 | 0 of 22 | 0 of 36 | 1.34 |

Bearing speed. Catalogue limit x 0.81 (SKF Table 39, preload A), r/min:

| Candidate | Grease | Oil-air |
|---|---|---|
| SKF 7005 CD/HCP4A | 34 830 | 54 270 |
| NSK 30BNR19HTSUMP3 | 25 920 | 29 970 |
| SKF 7006 CD/HCP4A | 30 780 | 45 360 |

Without a chosen candidate the check uses the lowest of the three, so on grease it passes a top speed of at most 21 600 r/min (25 920 / 1.2). At ratio 15 the check speed is 23 873 r/min (1.2 x 19 894), and the limit that the bike ratios reach is that of the NSK on grease. See "Limits of the checks" below for the NSK factor.

## Shortlist order: `gates-bound`

Command: `PYTHONPATH=src:tests python examples/bound_share.py --json docs/validation/bike_gates_bound_share.json` (LattePanda, 6491.5 s in all, ratio 12, margin 1.05, seed 0). The 3 lightest stage-1 designs that pass the limits in each of 6/4, 8/6 and 12/8: 9 designs, a screening map each. The bike requirement is the one above with `switching_frequency_hz` 20 kHz, `max_bus_voltage_v` 420 V and `max_length_m` 0.18 m.

| Pole set | Shares (drive torque at 50 r/min over `torque_upper`) | Regulated current over the 170 A device peak |
|---|---|---|
| 6/4 | 0.552, 0.454, 0.636 | 0.833, 0.879, 0.891 |
| 8/6 | 0.433, 0.569, 0.526 | 0.854, 0.755, 0.805 |
| 12/8 | 0.318, 0.426, 0.528 | 0.752, 0.792, 0.784 |

The shares run from 0.318 to 0.636. `BOUND_SHARE` in `srmapp.sizing.stage1` is the largest share x 1.1, 0.6356 x 1.1 = 0.699 (rounded). It orders the shortlist only and drops nothing. The regulated current is the winding current limit after the ripple derating, 75.2 to 89.1 % of 170 A at 20 kHz and 420 V. In all 9 scans the best density winding was not single-pulse (`single_pulse` false) and the scan found no feasible winding (`feasible` false at margin 1.05).

## Limits of the checks against the 10 to 15 % target

Each check is a pass or fail gate, not an accuracy claim. Where a gate has an error, this is its size and sign, as far as it is known.

- Rotor stress: the root model is valid inside its FE-derived box (V6, 1447 designs). Outside it the gate fails the design. Tip growth reads up to 9 % low against the FE (the unsafe sign); the gap-closure limit carries it (below).
- Frequency: above 2780 Hz the iron-loss factor is a held value, not a measurement, so those pole sets are removed before sampling. The factor itself is a measured-over-model ratio from one 18/12 machine.
- Bending: rigid simple supports leave out the bearing compliance. That reads the speed high (unsafe) by an amount with no cited stiffness. The Dunkerley sum, the missing stack stiffness and the mid-span lump read low (safe). The span allowance of 15 mm per end is a placeholder and may be short for a double-bearing set at each end (`docs/r5-sources.md` section 10). The 1.3 margin is not tied to a measured error. No measured bending speed of a small SRM rotor was found, so the figure is not validated.
- Bearing speed: the factor 0.81 is kept by owner decision (2026-11-28, block at light preload A). The NSK "...SUMP3" may be a medium-preload set. Then the factor is too high (unsafe). With the 0.65 factor the NSK grease limit is 20 800 r/min and the top speed is about 17 333 r/min, not 21 600 r/min. This is an owner input: order the NSK at light preload, or confirm the preload and its factor (`docs/r5-sources.md` section 11).
- Gap closure: the centrifugal-only path runs only when the rotor is at or below the bore temperature and the bore is at or above 20 degC, in both cases (the stator and rotor are one material, and 10JNEX900 has no expansion coefficient). Then the thermal part opens the gap, so the centrifugal part alone is an upper bound on closure. A hotter rotor gives `not_run`, which never blocks. Where the thermal part runs, the centrifugal growth is raised by 1 / (1 - 0.094) for the FE comparison. The limit is 0.5 x the air gap. In the 8/6 screening timing case the check was not run: the rating notes say there are no thermal expansion data for the stator and rotor materials.
- Current ripple: hard chopping at zero back-EMF, with V the highest bus voltage, is the safe side. It gives twice the ripple of soft chopping, and the hysteresis controller can chop hard (`soft = 0`), so hard chopping is the case that is sized. L is the lowest L_inc with the end winding at image factor 1.0, divided by 1 + `MEASURED_LU_GAP` (the model Lu reads 45 % high against the Krishnan 6/4 measurement). The inverter is not chosen. L between two map current nodes is the lower of the two nodes, which costs about 1 to 2 % of current on screening grids (an estimate, not measured). The derivation of the constant is in `docs/r3-sources.md` section 8.
- Rating at shaft torque: the loss torque counts all iron loss, with the iron factor, as drag. That is the safe side. The rated drop in torque is explained exactly by the loss torque (table above). The rating takes about 7x longer. A speed-up is an open Tracker item: reuse strokes within `DRAG_TOL`, and start the shaft top from the previous speed.
- Peak kW/kg is a band from rated to nominal. The peak-heat check (V4) covers one 14 s copper-dominated pulse. The cooling paths and a 30 s peak from warm have no measured check, and the continuous rating has none.
