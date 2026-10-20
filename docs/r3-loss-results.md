# R3 loss results: Materu 6/4 check and Yan region shares

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

Screening preset only (laptop, 2026-10-20, 4 workers; `full` run pending owner go-ahead). Rows T4.1 and T5.5, nominal
and shifted turn-on, M19 stand-in as above. Nothing is fitted: the width coefficients and band widths are the
literature values in `srmcore.post.cut_edge.CUT_PROCESSES`. Command:
`$env:PYTHONPATH="src;tests"; python -u examples\materu_losses_check.py --preset screening --workers 4 --rows 4:0 5:4 --json docs\r3-data\materu-cut-screening.json`
(about 45 min: 12 min for the map, about 5 min per stroke solve; the four process evaluations of a row share one
stroke solve through the cache). The full screening row set (10 rows, 20 stroke solves, about 2 h) was not run.

Iron error against the measurement; in brackets the error at the low and high end of the process's width-coefficient
range. R3 is the `unspecified` run (no edge multiplier).

| Row | R3 error | WEDM error (range) | punching error (range) | laser error (range) | Measured (W) |
|---|---|---|---|---|---|
| T4.1 nominal | -21 % | -23 % (-22 to -20) | -16 % (-21 to -10) | -14 % (-22 to -3) | 5.6 |
| T4.1 3.5 deg earlier | -24 % | -26 % (-25 to -23) | -19 % (-24 to -13) | -17 % (-25 to -7) | 5.6 |
| T5.5 nominal | -68 % | -68 % (-68 to -67) | -65 % (-68 to -63) | -64 % (-68 to -60) | 22.9 |
| T5.5 4.5 deg earlier | -71 % | -71 % (-71 to -70) | -69 % (-71 to -66) | -68 % (-71 to -63) | 22.9 |

Change of the computed iron loss against R3 at the nominal width coefficient: WEDM -2 %, punching +6 to +8 %, laser
+9 to +11 %. The one-sided range reported for an unspecified process (WEDM low to laser high) is -3.6 % to +34..41 %.

Reading:

- Punching and laser raise the loss by 6 to 11 %, inside the +5 to +15 % that spec §3 expected for these rotor and
  stator sizes. WEDM lowers it by about 2 % because its nominal width coefficient (0.3 mm) is below the as-sheared
  Epstein strips (1.4 mm) that the fitted loss data already contain.
- The cut-edge factor moves the error by 2 to 10 percentage points on T4.1 and 3 to 4 on T5.5. The sign is right
  (all errors stay negative and move toward zero for punching and laser), but it does not explain the gap: T5.5 stays
  at -64 to -71 % and T4.1 at -14 to -26 %. The remaining gap is the current shortfall, the steel stand-in and the
  3D effects discussed above; the cut-edge range at most closes a few percent of it.

8/6 (10JNEX900, same stroke as the Yan share cross-check, 3000 rpm, 6.14 N·m) cut-edge factor (hysteresis plus
excess, with over without the multiplier) and the area share of the damaged band per region:

| Process | Region | Factor | Band share |
|---|---|---|---|
| wedm | stator pole | 0.984 | 3.1 % |
| wedm | stator yoke | 0.968 | 1.6 % |
| wedm | rotor pole | 0.997 | 4.6 % |
| wedm | rotor yoke | 0.961 | 0.9 % |
| punching | stator pole | 1.097 | 8.6 % |
| punching | stator yoke | 1.061 | 8.5 % |
| punching | rotor pole | 1.118 | 8.9 % |
| punching | rotor yoke | 1.026 | 5.6 % |
| laser | stator pole | 1.138 | 8.6 % |
| laser | stator yoke | 1.092 | 8.5 % |
| laser | rotor pole | 1.164 | 8.9 % |
| laser | rotor yoke | 1.046 | 5.6 % |

The pole regions carry the larger factors and the yokes the smaller ones (a pole has more cut edge per area). The spec §3
estimate for the wide-part Materu 6/4 had the stator yoke highest; that is a different machine. Raw output: `docs/r3-data/materu-cut-screening.json`.

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
