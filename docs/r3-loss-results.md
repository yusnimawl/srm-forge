# R3 loss results: Materu 6/4 check and Yan region shares

Status: template. The numbers marked TBD are filled by the laptop run
(`$env:PYTHONPATH="tests"; python examples\materu_losses_check.py --json docs\r3-data\materu.json`, hours at `reference`).
Sources: `docs/r3-sources.md` section 4 (Materu, Tables 4 and 5) and section 5 (Yan et al. 2020).

## Setup

- Machine: the Krishnan/Materu 6/4 of `tests/krishnan_6_4.py` (book bore, packing 0.5), `reference` mesh, 2D plus the
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
| T4.1 | nominal / shifted | 955 | 1.07 / TBD | 0.446 / TBD | 5.6 | TBD | TBD | TBD | 2.0 | TBD | TBD | TBD |
| T4.2 | nominal / shifted | 729 | 1.54 / TBD | 0.629 / TBD | 9.6 | TBD | TBD | TBD | 4.0 | TBD | TBD | TBD |
| T4.3 | nominal / shifted | 615 | 1.83 / TBD | 0.768 / TBD | 10.4 | TBD | TBD | TBD | 6.0 | TBD | TBD | TBD |
| T4.4 | nominal / shifted | 550 | 2.13 / TBD | 0.888 / TBD | 10.5 | TBD | TBD | TBD | 8.0 | TBD | TBD | TBD |
| T4.5 | nominal / shifted | 486 | 2.54 / TBD | 1.051 / TBD | 10.70 | TBD | TBD | TBD | 11.3 | TBD | TBD | TBD |
| T5.1 | nominal / shifted | 2324 | 2.67 / TBD | 0.870 / TBD | 20.6 | TBD | TBD | TBD | 7.7 | TBD | TBD | TBD |
| T5.2 | nominal / shifted | 1806 | 3.28 / TBD | 1.067 / TBD | 11.3 | TBD | TBD | TBD | 11.6 | TBD | TBD | TBD |
| T5.3 | nominal / shifted | 1458 | 4.04 / TBD | 1.356 / TBD | 7.3 | TBD | TBD | TBD | 18.8 | TBD | TBD | TBD |
| T5.4 | nominal / shifted | 1150 | 4.94 / TBD | 1.712 / TBD | 15.5 | TBD | TBD | TBD | 29.9 | TBD | TBD | TBD |
| T5.5 | nominal / shifted | 1004 | 5.66 / TBD | 2.000 / TBD | 22.9 | TBD | TBD | TBD | 40.8 | TBD | TBD | TBD |

Reading: TBD.

## Region shares against Yan et al. 2020 (qualitative)

Different machine (4-phase 8/6, 50W470) and material from this repo's 8/6 (10JNEX900); compare the pattern only. The repo
8/6 is run at 3000 rpm on the stroke of half the envelope torque (300 V, 0.3 Ohm, I_max 20 A).

| Region | This 8/6 (%) | Yan et al. (%) |
|---|---|---|
| Stator yoke | TBD | 52.9 |
| Stator teeth | TBD | 23.9 |
| Rotor | TBD | 23.2 |

Reading: TBD.

## Preliminary screening run (laptop, 2026-10-19)

Preliminary. Screening mesh, two rows only (T4.1 and T5.5), M19 0.36 mm as the stand-in for Materu's steel. These
numbers do not replace the TBD table above.

| Row | turn-on | Peak meas / comp (A) | Iron meas / comp (W) | Error | Iron uncertainty | Cu meas / comp (W) |
|---|---|---|---|---|---|---|
| T4.1 | nominal | 1.07 / 0.76 | 5.6 / 4.41 | -21 % | +-39 % | 2.0 / 1.1 |
| T4.1 | 3.5 deg earlier | 1.07 / 1.07 | 5.6 / 4.25 | -24 % | +-39 % | 2.0 / 2.0 |
| T5.5 | nominal | 5.66 / 4.07 | 22.9 / 7.37 | -68 % | +-41 % | 40.8 / 21.4 |
| T5.5 | 4.5 deg earlier | 5.66 / 5.66 | 22.9 / 6.67 | -71 % | +-42 % | 40.8 / 50.2 |

Region shares of the repo 8/6 (10JNEX900), same run: stator yoke 40.7 %, stator teeth 30.0 %, rotor 29.2 %, against
Yan et al. 52.9 / 23.9 / 23.2 % (qualitative; different machine and material).

- The specification section 9 check (reference mesh, all rows) is still to run on the laptop.
- The iron shortfall at T5.5 is outside the stated uncertainty and is not explained yet.
- Candidate causes, none confirmed: the material stand-in; Materu's measured iron loss is a subtraction with an
  assumed 6 % stray term; the real lamination thickness is unknown (the classical term uses 0.36 mm); the M5d 2D flux
  deficit.
