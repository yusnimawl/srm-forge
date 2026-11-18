# Kiyota 10JNEX900 iron-loss check (tracker row 10a)

Goal: run the R3 iron-loss model on the measured points of Kiyota, Kakishima and Chiba 2014 (Table III and Fig. 16)
and replace `srmapp.cooling.K_IRON_HI` (2.0, R5 spec §2 item 2) with a value derived from the errors. Measurements
check, they never calibrate: the factor is a band edge, nothing is fitted inside the model.

Sources (git-ignored PDFs in `docs/sources/papers/`): Kiyota and Chiba 2012 (design, Fig. 7 drawing) and Kiyota,
Kakishima and Chiba 2014 (test). Readings: `tools/digitise_kiyota.py` (done).

## Machine (tests/kiyota_18_12.py)

18/12, 3 phases, 10JNEX900 0.10 mm stator and rotor. Cited (2012 Table II, 2014 Tables I and II): stator OD 264 mm,
rotor outer radius 91 mm, air gap 0.5 mm, stack 87.25 mm stator and 87.15 mm rotor (the model takes 87.2 mm), stator
pole taper 7.5° (2012 Fig. 6), 20 series turns per pole, 9 parallel 0.9 mm wires, slot fill 56 %, 650 V bus,
measured phase resistance 97.8 mΩ (20 °C assumed), tests at 75 °C coil end. Read off Fig. 7 (`digitise_kiyota.py`,
0.341 mm/px; the bore and rotor radius read 91.67 and 91.26 mm against 91.5 and 91.0 cited, so reading error about
±0.3 mm): stator pole arc 10.0°, stator taper 7.43° (cited 7.5° used), rotor pole arc 10.46°, rotor taper 1.52°,
shaft (rotor inner) radius 55.1 mm, rotor slot bottom radius 72.1 mm (rotor yoke 17.0 mm), stator slot bottom radius
115.7 mm (stator yoke 16.3 mm; the 2012 design study's point (b) has 15.5 mm, a sensitivity row). Assumed: fillets 0
(the drawing has rounded slot corners, not read), liner 0.3 mm, the 110 mm hub is the default shaft material, the
coil fills the half slot (clearance solved so the copper area 180 x π(0.45 mm)² = 114.5 mm² per coil side sits at
the cited 56 % fill). Built inside `waive_rules("self_starting")` if the validator asks (validation reference machine).
`ASSUMED` dict as in `tests/krishnan_6_4.py`. Fast test: the design validates and meshes at `screening`; unaligned
and aligned inductance at 10 A (2D plus end winding at image factor 1.5) printed against the measured 1.2 and 9.1 mH
(2014 Table II), no assertion on the gap (it is a check, not a gate).

## Points (examples/kiyota_losses_check.py)

| Point | r/min | Torque N·m | Peak A | RMS A | Copper kW | Iron and other kW |
|---|---|---|---|---|---|---|
| III (a) knee | 2768 | 209 | 240 | 137 | 6.8 | 0.7 |
| III (b) max power | 8700 | 113 | 205 | 130 | 6.0 | 4.4 |
| III (c) max efficiency | 7500 | 36 | 76 | 35.4 | 0.5 | 0.6 |
| Fig. 16 | 13 900 | P / ω for P = 14.68, 17.22, 21.94, 22.36, 30.03, 59.06, 99.46 kW | | | | 0.823, 0.944, 1.123, 1.260, 1.564, 3.348, 6.989 |

Map: the design at 20 turns, `full` preset, I_max 300 A, phase A, end winding added (image factor 1.5). Phase
resistance at 75 °C from 97.8 mΩ at 20 °C. Two strokes per point, both `min_copper_stroke` at 650 V:
1. torque: the measured torque;
2. current: the torque target at which the stroke's RMS current equals the measured RMS current (bisection), since the
   2D model gives more torque per ampere than the 3D machine (R4).
For each: `stroke_losses` (all phases, `cut_process="unspecified"`), iron W nominal and the cut-edge range,
`iron_uncertainty`, computed peak and RMS current. Ratio = measured iron-and-other / model iron. Electrical frequency
= rpm/60 x 12. JSON out (`--json`), table on stdout. `--preset`, `--workers`, `--cache-dir`, `--points`.

## Result and decision

Record in `docs/r3-loss-results.md` (new section) and V0 inputs in `docs/r5-sources.md`. `K_IRON_HI` becomes the
largest ratio of the stroke that matches the measured current, unless the ratios grow with frequency, in which case
it becomes a function of electrical frequency (stated, with the points). "Iron and other" holds stray losses too, so
the ratio over-states the iron error: the factor is pessimistic, which is the side a band edge must sit on.
