# R3 loss results: Materu 6/4 check, Kiyota 18/12 check and Yan region shares

Status: run 2026-10-19 on the laptop at the `full` preset, 6 workers, about 3 h
(`$env:PYTHONPATH="tests"; python examples\materu_losses_check.py --preset full --workers 6 --json docs\r3-data\materu.json`;
raw output in `docs/r3-data/materu.log` and `materu.json`). Owner ruling 2026-10-19: `full`, not `reference`. The 6/4
`reference` mesh has 1.2 M nodes (150-200 s per solve, about 70 h for the map and strokes, and out of memory at 10
workers on 16 GB), while `full` is within 0.25 % of `reference` in flux (M5a), far below the errors reported here.
Sources: `docs/r3-sources.md` section 4 (Materu, Tables 4 and 5) and section 5 (Yan et al. 2020).

## Setup

- Machine: the Krishnan/Materu 6/4 of `tests/krishnan_6_4.py` (book bore, packing 0.5), `full` mesh, 2D plus the
  analytic end-winding inductance at image factor 1.5 (`docs/m5d-krishnan-results.md`).
- Drive: 180 V d.c., phase resistance 3.4 Ohm, single pulse with a hysteresis current limit at the row's measured peak
  current, at the row's measured speed. Table 4 (flat-topped): advance 0 deg, conduction 18.05 deg. Table 5 (peaky):
  advance 11.95 deg, conduction 25.27 deg.
- Iron loss: 60 stroke angles per rotor pole pitch, rotor waveform over its own period, Bertotti fit per unit mass.
- Copper loss: 3 x 3.4 Ohm x I_rms^2, as Materu computed it, once with the measured rms and once with the computed rms.

## Assumptions

- **Angles.** Mechanical degrees. The advance is measured before the onset of pole overlap, which is the aligned
  position minus (stator arc + rotor arc)/2 = 30 deg (24 deg and 36 deg arcs); turn-on = onset - advance and
  turn-off = turn-on + conduction. Materu's text does not say whether the angles are mechanical or electrical.
- **Material.** M19 0.36 mm data, fitted at 0.36 mm (the loss data carry the thickness they were measured at). Materu's "E140" steel has no published loss curve. The M19 fit (grade C, test-only data) stands in, so the
  iron error includes this material gap, of unknown size.
- **Operating point.** The control is not described for the measured points; single-pulse operation with the speed set by
  the load is an inference. The computed peak and rms current are printed beside the measured ones, so a mismatch of the
  operating point shows up separately from the loss model.
- **Turn-on offset.** The nominal angles give computed currents about 30 % below the measured ones (the back-EMF limits
  the current at the stated turn-on). Each row is also run with the pulse (conduction angle kept) turned on the
  smallest number of degrees earlier that reaches the measured peak current. That a few degrees of real turn-on
  advance is the cause is a guess; the source does not confirm it. The `valid` column says whether the flux is back to
  zero before the next turn-on.
- **Measured iron loss** is a difference (total loss minus copper, friction and windage, and an assumed 6 % stray loss);
  the dissertation quotes cutting-stress increases of up to 25 %, and the Table 5 values are not monotonic. Its
  uncertainty is large and not stated.
- **2D flux deficit (M5d).** After the end-winding correction the 2D model under-predicts the flux linkage by 2.0 % at
  1 A and 11.4 % at 10 A (torque -10.9 % at 1 A, -16.9 % at 10 A). The measured points are at 1 to 6 A, where the
  deficit is small, but it is not zero; it lowers the computed B and so the computed iron loss slightly.

## Materu check

| Row | turn-on | rpm | Peak meas / comp (A) | rms meas / comp (A) | Iron meas (W) | Iron comp (W) | Error | Iron uncertainty | Cu meas (W) | Cu from meas rms (W) | Cu comp (W) | valid |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T4.1 | nominal | 955 | 1.07 / 0.77 | 0.446 / 0.332 | 5.6 | 4.61 | -18 % | 39 % | 2.0 | 2.0 | 1.1 | True |
| T4.1 | 3.5 deg earlier | 955 | 1.07 / 1.07 | 0.446 / 0.448 | 5.6 | 4.44 | -21 % | 39 % | 2.0 | 2.0 | 2.1 | True |
| T4.2 | nominal | 729 | 1.54 / 1.02 | 0.629 / 0.433 | 9.6 | 5.62 | -41 % | 39 % | 4.0 | 4.0 | 1.9 | True |
| T4.2 | 4.0 deg earlier | 729 | 1.54 / 1.54 | 0.629 / 0.626 | 9.6 | 5.37 | -44 % | 40 % | 4.0 | 4.0 | 4.0 | True |
| T4.3 | nominal | 615 | 1.83 / 1.28 | 0.768 / 0.520 | 10.4 | 6.64 | -36 % | 40 % | 6.0 | 6.0 | 2.8 | True |
| T4.3 | 4.0 deg earlier | 615 | 1.83 / 1.83 | 0.768 / 0.790 | 10.4 | 6.11 | -41 % | 41 % | 6.0 | 6.0 | 6.4 | True |
| T4.4 | nominal | 550 | 2.13 / 1.66 | 0.888 / 0.603 | 10.5 | 7.45 | -29 % | 41 % | 8.0 | 8.0 | 3.7 | True |
| T4.4 | 3.0 deg earlier | 550 | 2.13 / 2.13 | 0.888 / 0.871 | 10.5 | 7.39 | -30 % | 42 % | 8.0 | 8.0 | 7.7 | True |
| T4.5 | nominal | 486 | 2.54 / 2.54 | 1.051 / 0.763 | 10.7 | 8.11 | -24 % | 49 % | 11.3 | 11.3 | 5.9 | True |
| T5.1 | nominal | 2324 | 2.67 / 1.81 | 0.870 / 0.590 | 20.6 | 4.53 | -78 % | 39 % | 7.7 | 7.7 | 3.5 | True |
| T5.1 | 5.0 deg earlier | 2324 | 2.67 / 2.67 | 0.870 / 0.944 | 20.6 | 4.55 | -78 % | 39 % | 7.7 | 7.7 | 9.1 | True |
| T5.2 | nominal | 1806 | 3.28 / 2.31 | 1.067 / 0.759 | 11.3 | 5.12 | -55 % | 39 % | 11.6 | 11.6 | 5.9 | True |
| T5.2 | 4.5 deg earlier | 1806 | 3.28 / 3.28 | 1.067 / 1.168 | 11.3 | 5.18 | -54 % | 40 % | 11.6 | 11.6 | 13.9 | True |
| T5.3 | nominal | 1458 | 4.04 / 2.84 | 1.356 / 0.947 | 7.3 | 5.73 | -22 % | 40 % | 18.8 | 18.8 | 9.1 | True |
| T5.3 | 4.5 deg earlier | 1458 | 4.04 / 4.04 | 1.356 / 1.466 | 7.3 | 5.78 | -21 % | 41 % | 18.8 | 18.8 | 21.9 | True |
| T5.4 | nominal | 1150 | 4.94 / 3.57 | 1.712 / 1.230 | 15.5 | 6.62 | -57 % | 40 % | 29.9 | 29.9 | 15.4 | True |
| T5.4 | 4.5 deg earlier | 1150 | 4.94 / 4.94 | 1.712 / 1.883 | 15.5 | 6.30 | -59 % | 41 % | 29.9 | 29.9 | 36.1 | True |
| T5.5 | nominal | 1004 | 5.66 / 4.06 | 2.000 / 1.446 | 22.9 | 7.15 | -69 % | 41 % | 40.8 | 40.8 | 21.3 | True |
| T5.5 | 4.5 deg earlier | 1004 | 5.66 / 5.66 | 2.000 / 2.217 | 22.9 | 6.67 | -71 % | 42 % | 40.8 | 40.8 | 50.1 | True |

Reading:

- **Every computed iron loss is below the measurement**: -18 % to -44 % on the flat-topped rows (Table 4), -21 % to
  -78 % on the peaky rows (Table 5). Seven of the ten nominal rows are outside the stated iron uncertainty (39-49 %);
  T4.1, T4.5 and T5.3 are inside it.
- **The computed loss rises smoothly with current (4.5 to 8.1 W); the measured one does not** (Table 5: 20.6, 11.3, 7.3,
  15.5, 22.9 W from 2.7 to 5.7 A). Measured iron loss is a subtraction with an assumed stray term, so part of the
  spread is in the measurement, which no model can follow.
- **The operating point is not the cause.** Turning on 3-5 deg earlier reproduces the measured peak current, and the
  copper loss then matches on the flat-topped rows (2.1/2.0, 4.0/4.0, 7.7/8.0 W), but the iron loss barely moves (it
  falls slightly). The current gap at the stated angles is a separate, unexplained offset of a few degrees.
- **Likely main cause, not confirmed: no manufacturing build factor.** The model uses Epstein data for sheared strips;
  punched and stacked cores commonly lose 1.3-2x more (Materu himself quotes up to +25 % from cutting stress and
  stacking; the Newcastle 12/8 in `docs/r3-sources.md` measured far above FEA even with a build factor of 1.8). A
  factor of about 1.3-1.8 would bring Table 4 into agreement but not the scattered Table 5 rows. The engine has no
  build factor today; adding one is a decision for the owner (a calibrated knob, not a fix of the physics).
- Other candidates, none confirmed: the M19 stand-in for E140; the unknown real lamination thickness (classical term
  at 0.36 mm); the small 2D flux deficit at 1-6 A (M5d).
- The spec's "done when" asks for the error to be reported: it is, and it is larger than the stated uncertainty, so
  R3's iron-loss accuracy against measurement is an open finding.

## Region shares against Yan et al. 2020 (qualitative)

Different machine (4-phase 8/6, 50W470) and material from this repo's 8/6 (10JNEX900); compare the pattern only. The repo
8/6 is run at 3000 rpm on the stroke of half the envelope torque (300 V, 0.3 Ohm, I_max 20 A).

| Region | This 8/6 (%) | Yan et al. (%) |
|---|---|---|
| Stator yoke | 40.5 | 52.9 |
| Stator teeth | 30.2 | 23.9 |
| Rotor | 29.3 | 23.2 |

Reading: run at 3000 rpm and 6.15 N m (23.6 W of iron loss). The ranking matches (stator yoke largest, then stator
teeth, then rotor); the yoke share is lower than Yan's. Different geometry, material and operating point, so this is a
pattern check only.

## Cut-edge factor (R3c)

Screening preset only (laptop, 2026-10-20; `full` run pending owner go-ahead). Numbers regenerated after the band
fraction was made independent of the element size (sub-triangle sampling), from the cached map and strokes. All ten
rows, nominal and shifted turn-on, M19 stand-in as above (T4.1 and T5.5 in `docs/r3-data/materu-cut-screening.json`,
the other eight in `docs/r3-data/materu-cut-screening-rest.json`, same command with `--rows 4:1 4:2 4:3 4:4 5:0 5:1 5:2 5:3 --skip-yan`). Nothing is fitted: the width coefficients and band widths are the
literature values in `srmcore.post.cut_edge.CUT_PROCESSES`. Command:
`$env:PYTHONPATH="src;tests"; python -u examples\materu_losses_check.py --preset screening --workers 4 --rows 4:0 5:4 --json docs\r3-data\materu-cut-screening.json`
(about 45 min cold: 12 min for the map, about 5 min per stroke solve; the four process evaluations of a row share one
stroke solve through the cache; about 3 min with the map and strokes cached, `--cache-dir`).

Iron error against the measurement; in brackets the error at the low and high end of the process's width-coefficient
range. R3 is the `unspecified` run (no edge multiplier).

| Row | R3 error | WEDM error (range) | punching error (range) | laser error (range) | Measured (W) |
|---|---|---|---|---|---|
| T4.1 nominal | -21 % | -23 % (-24 to -21) | -17 % (-17 to -7) | -15 % (-16 to +3) | 5.6 |
| T4.1 3.5 deg earlier | -24 % | -25 % (-27 to -23) | -20 % (-20 to -9) | -18 % (-19 to -0) | 5.6 |
| T5.5 nominal | -68 % | -68 % (-69 to -67) | -66 % (-66 to -61) | -65 % (-65 to -57) | 22.9 |
| T5.5 4.5 deg earlier | -71 % | -71 % (-72 to -70) | -69 % (-69 to -64) | -68 % (-68 to -60) | 22.9 |
| T4.2 nominal | -44 % | -45 % (-46 to -43) | -40 % (-40 to -33) | -39 % (-40 to -26) | 9.6 |
| T4.2 4.0 deg earlier | -43 % | -44 % (-45 to -42) | -39 % (-39 to -31) | -38 % (-38 to -24) | 9.6 |
| T4.3 nominal | -33 % | -34 % (-35 to -32) | -29 % (-29 to -20) | -27 % (-28 to -11) | 10.4 |
| T4.3 4.0 deg earlier | -41 % | -42 % (-43 to -40) | -37 % (-37 to -28) | -35 % (-36 to -21) | 10.4 |
| T4.4 nominal | -27 % | -29 % (-30 to -27) | -23 % (-23 to -13) | -21 % (-22 to -4) | 10.5 |
| T4.4 3.0 deg earlier | -29 % | -31 % (-32 to -29) | -25 % (-25 to -15) | -23 % (-24 to -6) | 10.5 |
| T4.5 nominal | -24 % | -25 % (-27 to -23) | -20 % (-20 to -8) | -17 % (-19 to +1) | 10.7 |
| T5.1 nominal | -78 % | -78 % (-79 to -78) | -77 % (-77 to -74) | -76 % (-76 to -71) | 20.6 |
| T5.1 5.0 deg earlier | -79 % | -79 % (-79 to -78) | -77 % (-77 to -74) | -76 % (-77 to -71) | 20.6 |
| T5.2 nominal | -56 % | -56 % (-57 to -55) | -53 % (-53 to -47) | -52 % (-52 to -41) | 11.3 |
| T5.2 4.5 deg earlier | -55 % | -56 % (-57 to -54) | -52 % (-52 to -45) | -51 % (-51 to -39) | 11.3 |
| T5.3 nominal | -24 % | -25 % (-27 to -23) | -19 % (-19 to -8) | -17 % (-18 to +2) | 7.3 |
| T5.3 4.5 deg earlier | -19 % | -20 % (-22 to -17) | -13 % (-13 to -0) | -11 % (-12 to +11) | 7.3 |
| T5.4 nominal | -57 % | -58 % (-59 to -56) | -54 % (-54 to -48) | -53 % (-54 to -42) | 15.5 |
| T5.4 4.5 deg earlier | -59 % | -59 % (-60 to -58) | -56 % (-56 to -49) | -55 % (-55 to -43) | 15.5 |

Change of the computed iron loss against R3 at the nominal width coefficient: WEDM -1 to -2 %, punching +5 to +7 %,
laser +8 to +10 %. The one-sided range reported for an unspecified process (WEDM low to laser high) is -3.7 % to
+30..37 %.

Reading:

- Punching and laser raise the loss by 5 to 10 %, inside the +5 to +15 % that spec §3 expected for these rotor and
  stator sizes. WEDM lowers it by 1 to 2 % because its nominal width coefficient (0.3 mm) is below the as-sheared
  Epstein strips (1.4 mm) that the fitted loss data already contain.
- Per row. At the nominal width coefficients every error stays negative, on all ten rows. Over the laser range
  three rows reach zero: T4.1 (+3 % at nominal turn-on, -0.3 % shifted), T4.5 (+1 %) and T5.3 (+2 % nominal,
  +11 % shifted; punching high also reaches -0 % there). These are the rows that were already inside the stated
  iron uncertainty. The other seven (T4.2 to T4.4 at -4 to -26 % at best, T5.1, T5.2, T5.4 and T5.5 at -39 to -71 %
  at best, all at the laser high end) are not explained by the cut edge. The remaining gap is the current shortfall, the steel stand-in and the
  3D effects discussed above.

8/6 (10JNEX900, 3000 rpm, 6.14 N·m, 23.8 W; a separate run from the Yan share cross-check above, which differs slightly at 6.15 N·m, 23.6 W) cut-edge factor (hysteresis plus
excess, with over without the multiplier) and the area share of the damaged band per region:

| Process | Region | Factor | Band share |
|---|---|---|---|
| wedm | stator pole | 0.988 | 3.6 % |
| wedm | stator yoke | 0.975 | 2.9 % |
| wedm | rotor pole | 0.993 | 3.8 % |
| wedm | rotor yoke | 0.967 | 1.8 % |
| punching | stator pole | 1.100 | 8.8 % |
| punching | stator yoke | 1.049 | 7.3 % |
| punching | rotor pole | 1.122 | 9.3 % |
| punching | rotor yoke | 1.014 | 4.6 % |
| laser | stator pole | 1.142 | 8.8 % |
| laser | stator yoke | 1.076 | 7.3 % |
| laser | rotor pole | 1.170 | 9.3 % |
| laser | rotor yoke | 1.031 | 4.6 % |

The pole regions carry the larger factors and the yokes the smaller ones. The poles also have the larger band
shares (8.8 and 9.3 % for punching, against 7.3 % in the stator yoke and 4.6 % in the rotor yoke); the factor is
loss-weighted, so where the loss sits inside each region adds to that. The spec §3
estimate for the wide-part Materu 6/4 had the stator yoke highest; that is a different machine. Raw output: `docs/r3-data/materu-cut-screening.json`.

## Angle convergence (`ANGLE_CONVERGENCE_REL`, LattePanda, 2026-11-10)

Total iron loss of the 8/6 (`make_8_6`, 10JNEX900, 1500 r/min, the stroke waveform of `tests/maps/test_stroke_convergence.py`) at 60, 120 and 240 stroke angles. Data: `docs/validation/angle_convergence.json`.

| Preset | 60 angles (W) | 120 angles (W) | 240 angles (W) | Error at 60 angles |
|---|---|---|---|---|
| full | 3.4814 | 3.5330 | 3.5379 | 1.61 % against the Richardson limit 3.5384 W (observed order 3.4) |
| screening | 3.4808 | 3.5516 | 3.5289 | at most 1.99 % (not monotone, so no extrapolation; largest gap to a finer count) |

`ANGLE_CONVERGENCE_REL` stays 0.02, now measured rather than a placeholder (owner, 2026-11-10). The screening values zig-zag, probably because the angles snap to the coarse band pitch. Coverage: one machine, one current waveform, one speed.

## Friction and windage (tracker row 10m, 2026-11-17)

The efficiency map and the R5 heat input now include air-gap windage and bearing friction (`srmapp.mechanical`;
sources, grades and bands in `docs/r3-sources.md` sections 6 and 7). Efficiency is output power over output power
plus copper, iron, windage and friction loss.

Reference 8/6 (`make_8_6`: rotor radius 40 mm, gap 0.4 mm, stack 100 mm, shaft 20 mm; placeholder bearing: two
deep groove ball bearings, 20 mm bore, 23.6 N rotor weight), nominal values and the band on their sum:

| Speed (rpm) | Re | lambda (1e-3) | Windage (W) | Friction (W) | Sum (W) | Band on the sum |
|---|---|---|---|---|---|---|
| 1000 | 89 | 18.3 | 0.018 | 0.031 | 0.049 | -27 / +27 % |
| 3000 | 266 | 10.6 | 0.28 | 0.093 | 0.37 | -35 / +35 % |
| 6000 | 532 | 6.93 | 1.47 | 0.185 | 1.65 | -38 / +38 % |
| 10000 | 887 | 5.29 | 5.17 | 0.309 | 5.48 | -39 / +39 % |
| 15000 | 1330 | 4.60 | 15.2 | 0.463 | 15.7 | -39 / +39 % |

- Re is 89 to 1330 here, so this machine runs at the low end of the measured table. Below Re 351 (up to about
  4000 rpm) lambda follows the report's -0.5 slope and the result carries a note; the windage there is under 0.5 W.
- Windage grows about as speed to the power 2.4 and passes the bearing friction between 1000 and 3000 rpm; friction is
  constant torque.
- Check of the implementation against its own source: the NASA rig (12 in cylinder) with each Table I row's air
  temperature reproduces the printed windage power within +0.7 to +2.2 % for 15 rows between 241 and 15 337 rpm
  (`tests/thermal/test_thermal_windage.py` checks two of them against the 39.8 % band). This is a transcription check, not a
  validation: lambda was read from the same table.
- Not validated against a motor measurement: no measured windage of an SRM was found. The smooth-cylinder value is a
  lower bound for a salient rotor (no cited factor), so efficiencies read high by an unknown amount at high speed.
- Thermal: windage heats the rotor iron and friction the end caps; the rated set of the rating takes both at the
  top of their bands (budget row `mechanical_loss`). The rating's torque is not reduced by friction and windage
  (they take shaft torque, not winding heat).

## Kiyota 18/12, 10JNEX900 (tracker row 10a, LattePanda, 2026-11-18)

`examples/kiyota_losses_check.py` at `full`; machine `tests/kiyota_18_12.py`, readings `tools/digitise_kiyota.py`
(Kiyota and Chiba 2012 Fig. 7; Kiyota, Kakishima and Chiba 2014 Table III and Fig. 16; plan
`docs/superpowers/plans/2026-11-18-kiyota-iron-check.md`). The model's material is the laminations' own grade, so
this is the first check without a stand-in steel. Inductance at 10 A (2D plus end winding at image factor 1.5):
unaligned 1.02 mH against 1.2 measured, aligned 9.31 against 9.1.

Ratio = measured "iron and other losses" over the model's nominal iron loss, cut process `unspecified`. Stroke
"current" is the least-copper stroke whose RMS current equals the measured one; "torque" the one at the measured
torque (the Fig. 16 points have no measured current). Stator yoke 16.3 mm (Fig. 7) and 15.5 mm (2012 design study).

| Point | r/min | f_e | Stroke | RMS meas / model (A) | Measured (W) | Model (W) | Ratio, yoke 16.3 | Ratio, yoke 15.5 |
|---|---|---|---|---|---|---|---|---|
| III (a) knee, 209 N·m | 2768 | 554 Hz | current | 137 / 137 | 700 | 227 | 3.08 | 3.01 |
| III (c) max efficiency, 36 N·m | 7500 | 1.50 kHz | current | 35.4 / 35.6 | 600 | 218 | 2.76 | 2.72 |
| Fig. 16, 14.7 kW | 13 900 | 2.78 kHz | torque | - / 18.4 | 823 | 162 | 5.07 | 4.95 |
| Fig. 16, 17.2 kW | 13 900 | 2.78 kHz | torque | - / 21.0 | 944 | 170 | 5.55 | 5.30 |
| Fig. 16, 21.9 kW | 13 900 | 2.78 kHz | torque | - / 24.9 | 1123 | 208 | 5.40 | 5.53 |
| Fig. 16, 22.4 kW | 13 900 | 2.78 kHz | torque | - / 25.4 | 1260 | 207 | 6.08 | 5.90 |
| Fig. 16, 30.0 kW | 13 900 | 2.78 kHz | torque | - / 33.3 | 1564 | 225 | 6.96 | no stroke |

The torque stroke at (a) and (c) gives ratios within 6 % of the current stroke (3.17 and 2.91 at yoke 16.3). The
model's iron uncertainty (`iron_uncertainty`) is 27 to 39 %, the cut-edge range -4 to +39 % of the nominal.

Findings:

1. **The gap grows with frequency**: about 3 below 1.5 kHz, 5 to 7 at 2.78 kHz. Kiyota 2014 Fig. 14 shows the same
   trend for their own model (correction factor 4 at 1 kHz, 10 at 2.78 kHz) and names coefficient error at high
   frequency, additional losses and skin effect in the winding. The measurement holds stray and extra copper losses
   too, so the ratio over-states the iron error; it is the pessimistic side.
2. **Continuous conduction is modelled from srmapp 0.10.0** (2026-11-27, LattePanda, `docs/validation/kiyota_cc_16p3.json`,
   `kiyota_cc_15p5.json`). Before it, (b) and the Fig. 16 points at 59 and 99 kW had no stroke (best at (b): 55 N·m,
   57 A RMS against 130 A measured) and were left out of the ratios. Kiyota 2012 states that these outputs use
   continuous current, and the 2014 Fig. 17 current never returns to zero at 100 kW. The envelope now takes the
   periodic steady state where no single pulse completes. Every peak current is below the 300 A map top. The
   single-pulse rows (a), (c), f1 to f5 at 16.3 mm and f1 to f4 at 15.5 mm equal the 2026-11-18 rows exactly.
4. **How `K_IRON_HI` = 3.2 was chosen.** It is the largest measured-over-model ratio at or below 1.5 kHz, 3.170 (torque stroke at (a), yoke 16.3 mm), rounded up. The current-stroke rule would give 3.08. Above 1.5 kHz the curve is linear to 7.0 at 2.78 kHz.
3. Stator yoke 16.3 or 15.5 mm changes the ratios by at most 5 % at the single-pulse points (the table below); at
   15.5 mm the 30 kW point at 13 900 r/min (f5) also has a stroke, now in continuous conduction.

### Continuous-conduction points (2026-11-27)

Same method as the table above; "Conduction" is the stroke type the envelope chose.

| Point | r/min | Conduction | RMS meas / model (A), 16.3 / 15.5 | Peak meas / model (A), 16.3 / 15.5 | Model iron (W), 16.3 / 15.5 | Ratio, 16.3 | Ratio, 15.5 |
|---|---|---|---|---|---|---|---|
| III (b) 113 N·m, 103 kW, torque stroke | 8700 | continuous | 130 / 136.7 / 136.5 | 205 / 206.7 / 205.9 | 451 / 475 | 9.75 | 9.26 |
| III (b), current stroke (RMS 130 A asked) | 8700 | continuous | 130 / 136.7 / 117.4 | 205 / 206.7 / 188 | 451 / 430 | 9.75 | 10.23 |
| Fig. 16, 59 kW | 13 900 | continuous | - / 61.6 / 61.7 | - / 112 / 112 | 335 / 339 | 9.98 | 9.89 |
| Fig. 16, 99 kW | 13 900 | continuous | - / 111.7 / 112.0 | - / 188 / 188 | 545 / 574 | 12.83 | 12.17 |
| Fig. 16, 30.0 kW (f5), model torque 23.75 N·m at 15.5 mm | 13 900 | single pulse / continuous | - / 33.3 / 38.3 | - / 68 / 75 | 225 / 241 | 6.96 | 6.49 |

(The RMS and peak columns read: measured / model at 16.3 mm / model at 15.5 mm. At 16.3 mm the (b) current-stroke
row is the torque-stroke row.) The f5 stroke at 15.5 mm gives 23.75 N·m against the 20.63 N·m target (+15.1 %, 34.6 kW
instead of 30.0 kW), so its 6.49 ratio is taken at 15 % more torque; its 75 A peak is exactly the 2/8 current limit
(see the grid effect below).

Accuracy at (b): the torque stroke needs 136.7 A RMS at 16.3 mm and 136.5 A at 15.5 mm against 130 A measured, +5.1 %
and +5.0 %; the peak current matches within 1 % (206.7 and 205.9 A against 205 A). Two caveats. The torque stroke
overshoots the target: 117.66 N·m at 16.3 mm (+4.1 %) and 116.85 N·m at 15.5 mm (+3.4 %) against 113 N·m. And the RMS
depends on the current-limit grid: a stroke at 112.5 N·m needs 116.6 A, which is 10.3 % below the measured RMS, so
the RMS at (b) spans -10.3 % to +5.1 % depending on the grid. Both ends are inside the 10 to 15 % target, but the
spread is the size of the target.

**Failed acceptance line.** The "current" variant at (b), the stroke whose RMS equals the measured 130 A, does not
land within 0.5 %: it gives 136.7 A at 16.3 mm and 117.4 A at 15.5 mm (9.7 % under the measured RMS, 112.58 N·m,
0.4 % under the torque, 187.5 A peak). The cause is the current-limit grid of `min_copper_stroke` (default
`n_limits` = 8: limits k/8 of the 300 A map top, 37.5 A steps), not a boundary between single-pulse and continuous
strokes; both strokes are continuous. Measured on the cached maps (read-only probe, task review):

| Target (N·m) | n_limits | 16.3 mm | 15.5 mm |
|---|---|---|---|
| 112.5 | 8 | 112.65 N·m, 116.6 A RMS (psi_on 0.107) | 112.58 N·m, 117.4 A (psi_on 0.111) |
| 113 | 8 | 117.66 N·m, 136.7 A | 116.85 N·m, 136.5 A |
| 113 | 24 | 116.35 N·m, 123.9 A | 116.17 N·m, 124.2 A |

Both 112.5 N·m results sit at the 187.5 A limit. A 0.4 % change in torque target moves the RMS by about 16 %, so
the bisection in `match_rms` can only return the nearest stroke the grid holds. The plan's risk R2 expected the grid to
move the RMS by up to 3.5 %; here the 117.4 A row is 9.7 % under the measured 130 A, and the nearest alternative, 136.7 A, is 16.4 % above it.
The 10.23 ratio at 15.5 mm is a valid point at 0.4 % under the torque, closer to the measured torque than the torque
row (+3.4 %), but 9.7 % under the measured RMS.

Open item: the current-limit grid resolution. It moves the continuous-conduction RMS by up to about 16 % for a 0.4 %
change in torque, which matters for the bike search against the 10 to 15 % target.

**The three new points and `K_IRON_HI`.** Measured "iron and other" over model iron is 9.3 to 9.8 at (b), 9.9 to
10.0 at 59 kW and 12.2 to 12.8 at 99 kW, 6.5 at the 15.5 mm 30 kW point (at 15 % more torque than the measured). The `K_IRON_HI` curve (3.2 up to 1.5 kHz,
linear to 7.0 at 2.78 kHz): the continuous points at 9.3 to 12.8 sit above the 3.2 to 7.0 curve, so at high power the rated iron factor is on the unsafe side.
The measured figure also holds stray and AC copper loss, which the data do not separate, so the ratios over-state
the iron error. The continuous-point ratios (9.3 to 12.8 measured over model) are a factor of 9 to 13 against the owner's 10 to 15 % accuracy target for the iron loss, and the rated factor `K_IRON_HI` (3.2 to 7.0) does not cover them: this is the unsafe side. Changing `K_IRON_HI` is not in this plan; it stays an open item.

**Mutual coupling is not modelled.** In continuous conduction every phase carries current at every angle (all three
phases of the 18/12; on an 8/6 the phases overlap far more than in single pulse). The maps hold one excited phase and
the envelope adds the phase torques with no coupling. Krishnan (Ch 6) asks for a coupled model once phase currents
overlap more than 30 to 40 % of the period, where the mutual flux reaches about 10 % of the phase flux. So the
continuous strokes carry a coupling error that is not measured and is larger than for single pulse; this is a risk to
the 10 to 15 % target. The loss path solves all phases together (`srmcore.maps.stroke.stroke_fields`), so the iron
loss sees the coupled field; the drive torque and flux do not. Bike motor v1 part 4 measures the coupling on the
winner with the overlap map.

**Winding choice (8/6 screening density case).** Density mode picks the feasible winding with the most equivalent
turns, and continuous conduction makes high-turn windings feasible. With the auto winding the branch picks 500 turns
(the scan's limit) where main picks 242; torque at 750 r/min falls from 40.7 to 30.6 N·m, speeds above 3000 r/min gain,
and the evaluation takes 367 s instead of 58 s. With the same 242-turn winding on both trees, 300 and 750 r/min stay
single pulse and equal main bit for bit, and every faster speed has more torque (6000 r/min: 1.78 to 9.03 N·m). The
case material is M19 (no loss data), so no rated evaluation was timed and `RATING_BUDGET_S` is unchanged. Open owner
decision: whether density mode should prefer windings that are feasible in single pulse until the mutual coupling
under continuous conduction is measured. The numbers behind this paragraph, per speed for the auto and the fixed 242-turn winding, are in `docs/validation/cc86_8_6_density.json`.

## Preliminary screening run (laptop, 2026-10-19)

Preliminary. Screening mesh, two rows only (T4.1 and T5.5), M19 0.36 mm as the stand-in for Materu's steel. These
numbers are superseded by the `full` run above.

| Row | turn-on | Peak meas / comp (A) | Iron meas / comp (W) | Error | Iron uncertainty | Cu meas / comp (W) |
|---|---|---|---|---|---|---|
| T4.1 | nominal | 1.07 / 0.76 | 5.6 / 4.41 | -21 % | +-39 % | 2.0 / 1.1 |
| T4.1 | 3.5 deg earlier | 1.07 / 1.07 | 5.6 / 4.25 | -24 % | +-39 % | 2.0 / 2.0 |
| T5.5 | nominal | 5.66 / 4.07 | 22.9 / 7.37 | -68 % | +-41 % | 40.8 / 21.4 |
| T5.5 | 4.5 deg earlier | 5.66 / 5.66 | 22.9 / 6.67 | -71 % | +-42 % | 40.8 / 50.2 |

Region shares of the repo 8/6 (10JNEX900), same run: stator yoke 40.7 %, stator teeth 30.0 %, rotor 29.2 %, against
Yan et al. 52.9 / 23.9 / 23.2 % (qualitative; different machine and material).

Superseded by the `full` run above (screening and `full` agree within about 5 % on these two rows).
