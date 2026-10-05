# M5d results: measured Krishnan 6/4

## Summary

srmcore's 2D map of the Krishnan/Materu 6/4 (NGSolve, `reference` mesh) matches the measured aligned inductance at 1 A (-2.6 %, within the 10 % test bound) but falls short of the measurement as the machine saturates: La is -15.1 % at 10 A and -21.6 % at 20 A, and the stroke-averaged torque is -16.9 % at 10 A and -28.5 % at 20 A. The 2D unaligned inductance is +13 % to +29 % above the measurement (45.7 mH against 35.5-40.7 mH). The analytic end-winding hook (5.80 mH per phase, midpoint of the free-air and iron-image bounds) improves La (10 A: -15.1 % to -11.4 %; 20 A: -21.6 % to -15.0 %) and leaves T_avg unchanged, but it moves Lu away from the measurement (10 A: +13.0 % to +27.3 %), because the 2D model with the coil packed against the yoke already over-predicts Lu. The torque deficit has two parts: about 9 % of the measured torque at 20 A (2.5 % at 10 A) comes from the too-high 2D Lu, which inflates the unaligned coenergy, and the rest follows the saturated La. The residual La deficit at high current is not explained by the 2D lamination curves alone or by the end winding; it is outside the stated model uncertainty (2.6-4.0 % for La at 10-20 A, 3.3-6.3 % for T_avg).

## Source and machine

Data: P. N. Materu, PhD dissertation, Virginia Tech, 1989, Table 1 p. 41 and Appendix A pp. 287-288, reprinted as Table 2.3 in Krishnan (2001). Measured La 879 / 155 / 89 mH, Lu 35.5 / 40.7 / 35.6 mH and T_avg 0.90 / 20.3 / 41.6 N·m at 1 / 10 / 20 A. Materu's own 2D FEA: La 843 / 133 / 75.5 mH, Lu 25.8 mH, T_avg 0.80 / 18.5 / 37.8 N·m. The dissertation and the book disagree on the bore (122.0 vs 102.06 mm) and back iron (10.15 vs 10.515 mm); the book values are used (they reproduce Materu's FEA at 1 A) and the dissertation values are a budget row. See the spec `docs/superpowers/specs/2026-10-05-m5d-krishnan-6-4-design.md`.

Assumed fields (`tests/krishnan_6_4.py`, `ASSUMED`):

- bore: book 102.06 mm / back iron 10.515 mm; dissertation 122.0 / 10.15 mm as a budget row.
- shaft 28.56 mm and rotor pole height 27.25 mm from the dissertation; rotor yoke derived (9.25 mm).
- coil: packed against the yoke, bundle packing 0.5 (175 mm² copper in 350 mm²); 0.35-0.65 as a budget row. Solved clearance 21.46 mm; coil build 29.9 mm, depth 11.7 mm, span 51.7 mm.
- slot liner 0.3 mm (not in the source); fillets and tapers 0.
- materials: M19 (book); the dissertation names "E140 steel", not in the library; steel_1010 as a crude bound.
- built inside `waive_rules('self_starting')` (stator arc 24 deg < 30 deg).

Mesh preset `reference` for the primary table; the other budget rows use `full`. Solver NGSolve.

## Results

| Quantity | I (A) | Measured | Materu FEA | 2D | 2D + end winding | Error before | ± before | Error after | ± after |
|---|---|---|---|---|---|---|---|---|---|
| La (mH) | 1 | 879 | 843 | 855.9 | 861.7 | -2.6 % | 13.1 % + meas. n/s | -2.0 % | 13.4 % + meas. n/s |
| La (mH) | 10 | 155 | 133 | 131.6 | 137.4 | -15.1 % | 1.4 % + meas. n/s | -11.4 % | 2.6 % + meas. n/s |
| La (mH) | 20 | 89 | 75.5 | 69.81 | 75.62 | -21.6 % | 1.9 % + meas. n/s | -15.0 % | 4.0 % + meas. n/s |
| Lu (mH) | 1 | 35.5 | 25.8 | 45.73 | 51.53 | +28.8 % | 22.9 % | +45.2 % | 28.3 % |
| Lu (mH) | 10 | 40.7 | 25.8 | 46.01 | 51.81 | +13.0 % | 21.3 % | +27.3 % | 26.1 % |
| Lu (mH) | 20 | 35.6 | 25.8 | 45.72 | 51.53 | +28.4 % | 22.9 % | +44.7 % | 28.4 % |
| T_avg (N·m) | 1 | 0.9 | 0.8 | 0.8016 | 0.8016 | -10.9 % | 16.7 % + meas. n/s | -10.9 % | 16.7 % + meas. n/s |
| T_avg (N·m) | 10 | 20.3 | 18.5 | 16.86 | 16.86 | -16.9 % | 3.3 % + meas. n/s | -16.9 % | 3.3 % + meas. n/s |
| T_avg (N·m) | 20 | 41.6 | 37.8 | 29.73 | 29.73 | -28.5 % | 6.3 % + meas. n/s | -28.5 % | 6.3 % + meas. n/s |

"meas. n/s": the measurement scatter is not stated for that quantity and is not in the ± column. Raw output: `docs/m5d-data/krishnan_6_4_check.txt`.

## End-winding correction

End winding per phase (`srmcore.maps.end_winding.end_winding_inductance`): 3.87 mH with image factor 1 (coil in free air), 7.74 mH with image factor 2 (coil against a permeable end face); the reported correction is the midpoint, 5.80 mH. It adds 4.2 % to the corrected La and 11.2 % to the corrected Lu at 10 A. The reference line from Seward et al. (cited by Materu) is a 3D end leakage of 7.5 % of La and 35 % of Lu; our end winding alone is below that for both, and it is only the end-turn part (iron-end fringing is not modelled). T_avg is unchanged by a constant added inductance (torque is the derivative of coenergy at fixed current with respect to angle).

## Uncertainty budget

Per-row half-spreads, percent of measured at 1 / 10 / 20 A, combined as a worst-case sum (core spec §8.6):

| Row | La | Lu | T_avg |
|---|---|---|---|
| mesh (`full` vs `reference`) | 0.06 / 0.06 / 0.04 | 0.14 / 0.11 / 0.13 | 0.05 / 0.05 / 0.03 |
| material (M19 vs steel_1010) | 9.79 / 1.00 / 1.60 | 0.18 / 0.56 / 0.67 | 9.69 / 0.24 / 1.28 |
| geometry (book vs dissertation bore) | 3.13 / 0.20 / 0.19 | 10.90 / 9.60 / 10.68 | 6.91 / 2.39 / 3.60 |
| coil packing (0.35 vs 0.65) | 0.16 / 0.14 / 0.03 | 4.81 / 4.21 / 4.63 | 0.01 / 0.60 / 1.42 |
| end-winding model (image 1 vs 2, after only) | 0.22 / 1.25 / 2.17 | 5.45 / 4.75 / 5.43 | 0.00 / 0.00 / 0.00 |
| measurement | not stated | 6.8 % (non-monotonic measured Lu: half the 35.5-40.7 mH spread over its mean) | not stated |

The measured T_avg is computed from measured flux linkage (Materu p. 49), so its scatter follows La and Lu and is not independent.

## Discussion

- Measured T_avg is computed from measured flux linkage, not a torque sensor, so the torque comparison repeats the La/Lu comparison and is not an independent check.
- T_avg = 12 · (W′_aligned − W′_unaligned) / 2π depends on both La and Lu. Our 2D Lu is linear and too high, which inflates W′_unaligned and lowers T_avg. With W′_u = ½ · Lu · i², the Lu part is 12/(2π) · ½ · (Lu,2D − Lu,meas) · i²: at 20 A, 1.910 · ½ · (45.72 − 35.6) mH · 400 A² = 3.9 N·m (9.3 % of 41.6 N·m); at 10 A, 0.51 N·m (2.5 % of 20.3 N·m); at 1 A, 0.01 N·m (1.1 % of 0.90 N·m). That is about a third of the -28.5 % at 20 A; the rest follows the saturated-La deficit (-21.6 %). It also helps explain why Materu's FEA sits closer on torque: its Lu (25.8 mH) is below the measured Lu, and its saturated La at 20 A (75.5 mH) is higher than ours (69.8 mH).
- At 1 A (linear), the measured inductances imply 12/(2π) · ½ · (0.879 − 0.0355) H · 1 A² = 0.81 N·m, but the tabulated measured T_avg is 0.90 N·m. The measured torque is about 11 % above what the measured inductances imply, which is relevant to the -10.9 % at 1 A.
- Measured La at 20 A (89 mH) implies a flux of about 3.3 mWb (ψ/N). If all linked flux crossed the pole, that is about 2.6 T over the stator pole (21.4 × 60.4 mm) and in the 10.5 mm yoke halves, above the saturation polarisation of any steel; this is an upper bound, because slot and end leakage carry part of the linked flux. The deficit is therefore unlikely to come from the M19/steel_1010 lamination curves alone, and the budget has no row for the Js of the unidentified "E140" steel. After the end-winding correction the 20 A La is still 15 % low, outside the 4 % model uncertainty. Either unmodelled end flux (3D fringing) or the measurement (voltage integration drift at high current) carries the rest. This study cannot separate the two.
- Lu: our 2D value (45.7 mH, coil packed against the yoke) is above the measurement (35.5-40.7 mH) and well above Materu's 2D FEA (25.8 mH). The coil placement matters (packing row: ±4-5 %; the spec's "Spike results" section, screening mesh, shows Lu 37 to 45 mH moving the coil from the bore to the yoke; `docs/superpowers/specs/2026-10-05-m5d-krishnan-6-4-design.md`), and the geometry row (bore) is the largest (±10 %): the dissertation bore gives Lu 38 mH, which is close to the measurement. Adding the end winding to a 2D Lu that is already high makes the error worse (+13.0 % to +27.3 % at 10 A), so the planned expectation that the correction moves Lu toward the measurement does not hold for this model. Lu is not a reliable comparison until the coil geometry and bore are pinned down.
- La at 1 A is within 3 % of the measurement (and of Materu's FEA, 843 mH), but the material row alone is ±9.8 % there (M19 vs steel_1010), so that agreement carries a wide band.
- What remains uncorrected: 3D fringing of the iron ends (core spec §7.1: a fringing factor only after calibration against more measured data). This is the likely home of part of the saturated-La deficit (and the torque share that follows it) and is not modelled here; the Lu share of the torque deficit is a 2D-model and geometry issue, not an end effect.

## Reproduce

`$env:PYTHONPATH="tests"; .venv\Scripts\python -u examples\krishnan_6_4_check.py` (about 17 min on the owner's laptop). The slow test `tests/validation/test_krishnan_6_4.py` pins the `full`-preset table and the end-winding inductance.
