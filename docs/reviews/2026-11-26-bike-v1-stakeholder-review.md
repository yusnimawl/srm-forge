# Bike motor v1: stakeholder review (2026-11-26)

Seven read-only reviewer agents (tool end user, vehicle integrator, magnetics lead, thermal and mechanical lead, optimisation scientist, senior developer with the ponytail audit, test lead on ISO 21782) reviewed the Bike motor v1 path, and a product-manager agent merged their findings. The owner's open answers are on the Notion progress page. Hours are agent estimates.

## Issues that can change the recommended motor or make the order unsafe

| # | Issue | Evidence | Smallest fix | Code h / LattePanda h |
|---|---|---|---|---|
| 1 | Rotor stress is not a filter | `rotor_stress` is called only in `srmapp/thermal.py:511`; at 20 000 rpm 164 of 358 in-box sampled designs fail SF 1.5 (median SF 24/16 0.93, 12/8 1.54, 8/6 1.98, 6/4 2.78); 10.5 % of designs fall outside the model's validity box (generator yoke 0.50 x tip chord, box from 0.55) | Stage-1 reject unless status `ok` and SF >= 1.5; generator yoke floor 0.55; `evaluate_stage2` infeasible on a failing rating stress or closure | 5 / 0 |
| 2 | The shortlist picks the biggest motors | Sort key `torque_upper / mass.iron` (`pipeline.py:87`) grows with OD; top 40 of a bike run: 25 x 24/16, median OD 298 mm near the 350 mm default cap; same shortlist at every ratio | Lightest first, top k per pole set; expose pole sets; add 16/12 | 4 / 0 |
| 3 | Iron loss held flat above 2.78 kHz (unsafe side) | `cooling.py:28`; a 24/16 at 20 000 rpm runs at 5.3 kHz | Drop a pole set at a ratio when its top frequency is above 2.78 kHz; a ring test of 10JNEX900 lifts the cap | 1 / 0 |
| 4 | Maps re-solved per ratio; search preset defaults to `full` | `max_speed_rpm` is in the design hash (`identity.py:27`) and only used for a warning | Pin one `max_speed_rpm`; screening for the search, full for finalists | in #13 |
| 5 | Thermal errors hide as "not rated, feasible"; tracebacks lost | `evaluate.py:165` catches `ValueError`, and `InputError` is a `ValueError` | Catch only the two missing-data errors; thermal asked but not done = infeasible; log, stop after 3 same failures | 2 / 0 |
| 6 | Ranking rewards over-delivery and uses the worst-case stack only | `evaluate.py:93-97`, `pipeline.py:62-69` | Lightest design whose rated check holds; show nominal beside it; recommend only a design top under both | 3 / 0 |
| 7 | No continuous conduction | Kiyota 8700 rpm: model 55.6 N·m, 113 measured | Planned (branch `drive-continuous-conduction`) | 10 / 3.5 |
| 8 | No critical-speed or bearing-speed check | Hand estimate: first bending about 20 500 rpm for a 100 mm rotor, 25 mm shaft, 190 mm span, below 24 000 | Analytic bending >= 1.3 x max speed and a bearing DN limit as stage-1 filters | 8 / 0 |
| 9 | Gap closure cannot be computed and has no pass limit | 10JNEX900 has no expansion coefficient | Cited or JFE value plus a rule | 3 / 0 + data |
| 10 | Windage counted twice in the worst case | Kiyota "iron and other" already holds windage and friction; the `mechanical_loss` row adds them again | Leave the row out of the worst case while the Kiyota factor is on | 1 / 0 |
| 11 | Losses not taken off the power check; 28 kW at shaft or wheel | about 5 % at 30 kW on Kiyota | Shaft power after losses; wheel power / 0.93 | 2 / 0 |
| 12 | Current ripple ignored | about 50 A on 170 A at 300 V, 20 kHz, low Lu | Regulated + ripple/2 within the device limit | 2 / 0 |
| 13 | No bike search command, no resume, thin provenance | evaluations in memory (`pipeline.py:151-170`); `examples/v0_search.py` fixed at 10 kW | Command: requirements JSON in, shared maps over ratio x cooling, one result line per design, resume, systemd-run | 8 / 0 |
| 14 | Peak heat check against Kiyota | the end winding sets the 30 s peak | Planned (branch `r5e-v4-v5`) | 8 / 2.5 |

Later: thermal checks on more than 4 windings (finalists only), sampling the air gap once closure gates it, 3D end effects on the winner if stack / OD < 0.5, a repeated-peak duty cycle, fatigue, retention and G2.5 balancing in the test pack. Dropped for v1: web form fixes, the stress line in the UI, Losses tab labels, a single-pulse plot, HIL/SIL.

## Conflicts resolved by the product manager

- HIL plant shared by the emulator and the SIL: it does not change the motor; off the bike path.
- Windage: fix the double count only; no new windage model.
- The 19 % measured torque gap is not margin. On Kiyota, with the owner's steel, the model reads torque about 5 % high; the 10 % torque floor covers it.
- A frequency cap at 2.78 kHz, not a separate 24/16 rule.
- Ratio 15 stays in the search (shared maps make it cheap), but no order without a gearbox quote: stock planetaries for about 200 N·m top out near 7000 rpm input.
- The thermal test is not an order blocker if the margin is kept and thermocouples are wound in.

## Findings from the two plans

- Continuous conduction (prototype on the Kiyota `full` map): best torque at 8700 rpm 55.6 to 145.9 N·m; least-copper RMS at 113 N·m 136.7 A against 130 A measured (5 %); the 59 and 99 kW points at 13 900 rpm become reachable. Single-pulse strokes keep their numbers bit for bit. Risk: the winding scan gets about 2.7 x slower.
- Peak heat (V4): the hand adiabatic rise is 40.56 K against 39.5 +- 0.4 K read; the result is decided by the iron heat capacity, which is zero today (coil end 49.2 K, about 25 % hot; 41.6 K with 438 J/(kg K)). The thermal mesh error is at most 0.26 K at `screening` and 0.16 K at `full` on the 8/6, under the 0.5 K tolerance.

## Test plan outline (ISO 21782)

Part 3 holds the performance tests (5.1.1 efficiency, 5.1.2 continuous and heat, 5.1.3 torque-speed); Part 6 the operating-load tests (4.3.1 spin, 4.1.3 over speed, endurance); Part 5 the motor-system endurance, surge and over speed with a rank. Minimum ISO accuracy gives about +-18 to 21 % on the loss at 28 kW, so the 10 to 15 % target needs a class 0.05 torque flange and a 0.05 % power analyser. Calibrate on the static and coast-down tests, then predict the heat run and the efficiency points blind from a frozen predicted test sheet. Thermocouples must be wound in by jystator; they cannot be added after varnishing.
