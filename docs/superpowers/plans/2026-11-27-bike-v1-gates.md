# Gates, ranking and speed checks (Bike motor v1, parts 0 and 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Implementers: Sonnet. Reviewers (spec and code, after each task and at the end): Opus.

## Revised 2026-11-28

Main moved after this plan was written (PR #45, PR #46 and the owner decisions of 2026-11-27 and 2026-11-28).

1. D9 dropped: Kiyota's "iron and other" leaves the mechanical loss out (Diagnosis 7), so nothing is counted
   twice. Task 5 has no code.
2. D6: the drag torque takes the mechanical loss of the set, so the rated set takes the high end of both bands.
3. D11, Task 12, Diagnosis 12: the owner's three angular-contact candidates replace the Koyo 60 series. The check
   blocks.
4. The "Owner decision" question is gone (answered 2026-11-28). The section now lists the decisions the plan follows.
5. D10 and Task 11: the span allowance is checked against the candidates, and `BearingSetup.placeholder` keeps its
   meaning.
6. Task 10: the ranking says that its peak kW/kg is a band from rated to nominal (owner, 2026-11-28 item 2).
7. Task 1: the line 190 assertion becomes a containment check, because Tasks 6 and 13 add notes to the same error.
8. Task 14: the main baseline is srmapp 0.11.0 (iron heat capacity, end-winding residual). The loss torque is the
   only expected cause of a change.
9. Versions: srmapp 0.11.0 to 0.12.0, srmweb 0.12.1 to 0.12.2, `web/` stays 0.12.0, srmcore stays 0.8.0.
10. CI: the fast suite runs as four parts (turns, evaluate, app, rest). New test files land in `app`. Task 17
    records each part.
11. Sources: the bending and bearing-speed sources go to `docs/r5-sources.md` sections 10 and 11 (core spec §11,
    2026-11-27).
12. Hours: 36.5 attended, about 40.5 elapsed.

**Goal:** The search keeps only designs that meet the owner's hard limits, ranks the lightest design that holds its
rated check first, and stops hiding thermal errors. Parts 0 and 1 of the Bike motor v1 path (roadmap spec §0): rotor
stress, iron-loss frequency cap, total length, shortlist order, thermal errors, objective, windage double count
(checked: none), shaft power after losses, current ripple, single-pulse preference, first bending speed, bearing speed
and air-gap closure.

**Done when:** every task below is merged to main with CI green (fast suite, all four parts, on 3.12 and 3.14, slow
suite run on the branch), the LattePanda runs are recorded in `docs/bike-v1-gates-results.md`,
`docs/reports/bike-v1-0.md` and `docs/reports/bike-v1-1.md` are on main, and no item of this plan is left for later
except the open items listed at the end.

**Architecture:** srmapp only. A new module `src/srmapp/limits.py` holds the closed-form hard limits (rotor stress,
iron-loss frequency, first bending, bearing speed, air-gap closure) as `Limit` records. `run_search` applies them
after stage 1 and before the shortlist. `evaluate_stage2` applies them to the chosen machine and makes a failing
design infeasible. The thermal context asks the stroke for the shaft torque plus the loss torque. The winding scan
lowers each winding's current limit by half the switching ripple and ranks single-pulse windings first in density
mode. srmcore does not change.

**Sources:** roadmap spec §0 parts 0 and 1 (`docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`). Core spec
§11 rows of 2026-11-26 (bike target), 2026-11-27 (hard limits, bearing candidates) and 2026-11-28 (after the peak-heat
check V4). Stakeholder review issues 1 to 3, 5, 6, 8 to 12 (`docs/reviews/2026-11-26-bike-v1-stakeholder-review.md`).
`docs/reports/bike-v1-2.md` (continuous conduction). `docs/bearing-candidates.md` (bearing limits).

## Global constraints

- srmcore unchanged: no edit under `src/srmcore/`, `ENGINE_REVISION` unchanged, `python tools/engine_digest.py`
  passes, srmcore stays 0.8.0 (so `VALIDATED_VERSIONS` and the 2D-verified label are not touched). No map, overlap,
  stroke or field cache key changes.
- Worktree `/home/server/srm-forge-gates`, branch `bike-gates`. Run Python as
  `PYTHONPATH=src:tests /home/server/srm-forge/.venv/bin/python` (the shared venv imports the main checkout otherwise).
- Long runs (over about 10 min) go through `systemd-run --user --unit=NAME --collect -p WorkingDirectory=... ...`,
  one heavy job at a time on the LattePanda (check `systemctl --user list-units --state=active` first).
- `tests/app/envelope_reference.py` is a frozen copy: do not edit it. The winding-scan equality tests
  (`tests/app/test_app_scan_equality.py`) must pass unedited.
- A test literal that changes is updated in the same commit, with old value, new value and reason in the commit
  message. The expected changes are listed per task. Any other change: stop and report to the controller.
- Every new or changed rule cites its source in a code comment, `docs/r3-sources.md` or `docs/r5-sources.md`. Numbers
  with no cited source are named placeholders and the evaluation says so in a note.
- CI runs the fast suite as four parts side by side (`turns`, `evaluate`, `app`, `rest`; `.github/workflows/ci.yml`),
  each with a 60 min job limit. New `tests/app` files land in `app`. Keep new fast tests on synthetic maps and fakes.
- Comments explain the code as it is. No plan history in comments. Prose in docs follows `docs/writing-plan.md`.

## Diagnosis (2026-11-27, probes on the LattePanda, not committed)

Bike requirement used by the probes: 30 kW at the shaft, 12 kW continuous, 300 V, 170 A, stator OD at most 200 mm,
10JNEX900 stator and rotor, base speed max/3, density mode. Top speed 150 km/h on a 0.60 m tyre is 1326 r/min at the
wheel, so 10 610, 15 915 and 19 894 r/min at total ratios 8, 12 and 15.

### 1. Rotor stress (review issue 1)

`rotor_stress` runs only inside the rating (`src/srmapp/thermal.py:511`). The generator sets the rotor yoke to
0.50 to 1.00 of the rotor pole tip chord (`src/srmapp/sizing/generator.py:50`). The stress model's box starts at 0.55
(`_FIT_YOKE`, `src/srmcore/post/rotor_stress.py:32`). 250 samples per ratio, 50 per pole set:

| Pole set | Outside the box, yoke floor 0.50 | Outside, floor 0.55 | In box with SF < 1.5, ratio 15 |
|---|---|---|---|
| 6/4 | 8 (yoke) | 0 | 0 of 50 |
| 8/6 | 3 (yoke) | 0 | 0 of 50 |
| 12/8 | 6 (3 yoke, 3 free ring span) | 5 (free ring span) | 0 of 45 |
| 24/16 | 2 (yoke) | 0 | 21 of 50 |
| 16/12 (q = 4) | 33 (32 pole arc) | 32 (pole arc) | 2 of 18 |

With the 200 mm OD limit the safety factor binds on 24/16 only. The 0.55 floor puts every 6/4, 8/6 and 24/16 sample
in the box. The 16/12 rotor pole arc is normalised by the swept 3-phase limit for 12 rotor poles
(`_FIT_PHASES[12] = 3`), so 64 % of the 16/12 samples have narrower poles than the FE sweep covered.

### 2. Iron-loss frequency (review issue 3)

`K_IRON_HI` stops at 2780 Hz and is held flat above it (`src/srmapp/cooling.py:28`). Top stator electrical frequency
Nr x top speed / 60:

| Pole set | Ratio 8 | Ratio 12 | Ratio 15 |
|---|---|---|---|
| 6/4 | 0.71 kHz | 1.06 kHz | 1.33 kHz |
| 8/6 | 1.06 kHz | 1.59 kHz | 1.99 kHz |
| 12/8 | 1.41 kHz | 2.12 kHz | 2.65 kHz |
| 16/12 | 2.12 kHz | 3.18 kHz | 3.98 kHz |
| 24/16 | 2.83 kHz | 4.24 kHz | 5.31 kHz |

So 24/16 is above the cap at all three ratios (1.8 % above at ratio 8), and 16/12 is inside it at ratio 8 only.

### 3. Total length (owner limit with no code)

The core spec §11 row of 2026-11-26 item (11) sets total length at most 180 mm with both end windings, checked at
stage 1. `Requirements` has no length field and the generator samples stacks up to 1.2 x OD. Among stage-1 passing
designs, the share above 180 mm (stack plus 2 x (coil build + liner), as `active_volume`) is 19 to 56 % at ratio 15
and 32 to 50 % at ratio 8. This plan adds the limit (Task 3), because the gates and the ranking are wrong without it.

### 4. Shortlist order (review issue 2)

`run_search` sorts by `torque_upper / mass.iron` (`src/srmapp/pipeline.py:86`), which grows with size. The stage-1
torque bound is optimistic by a factor of about 2. Drive torque at 50 r/min over the bound at the map top:

| Map | Ampere-turns | Drive torque | Bound | Share |
|---|---|---|---|---|
| 8/6 M19 screening, `cache-timing` | 600 | 5.38 N·m | 14.07 N·m | 0.38 |
| 8/6 M19 screening, `cache-timing` | 3258 | 42.19 N·m | 76.42 N·m | 0.55 |
| Kiyota 18/12 full, `cache-kiyota` | 6000 | 288.5 N·m | 511.2 N·m | 0.56 |

So "lightest first" on the bare bound shortlists designs that have about half the torque they need. Stage 1 must
keep its no-false-drop contract, so the plan orders by a measured share instead of filtering (D4).

### 5. Thermal errors (review issue 5)

`evaluate_stage2` catches `ValueError` for the refusals (`src/srmapp/evaluate.py:165`). `InputError` and every other
`ValueError` from the thermal context land there too and give "not thermally rated" with the EM feasibility kept.
The two batch boundaries (`evaluate.py:124`, `:199`) keep only `str(exc)`, so the traceback is lost. A
`choose_turns` error other than `ScanCancelled` (`evaluate.py:135`) is not caught and stops the whole search.

### 6. Objective (review issue 6)

`SearchResult.pareto` (`pipeline.py:62`) is a front over rated continuous and rated peak kW/kg, so it rewards power
above the requirement and uses the rated set only. Evaluations hold no nominal kW/kg.

### 7. Windage double count (review issue 10): none (revised 2026-11-28)

`ThermalContext.load_at` adds the windage and the bearing friction at every torque (`thermal.py:319`). The row
`mechanical_loss` moves them to the high end of their bands, and the rated set has every row of `ROWS`
(`cooling.py:22`). The review assumed that the Kiyota iron factor `K_IRON_HI` already holds Kiyota's windage and
friction. It does not:

1. `K_IRON_HI` 3.2 is Table III (a): "iron and other" 0.7 kW over the model's iron loss, 3.08 with the current
   stroke (227 W) and 3.17 with the torque stroke, rounded up (`docs/r3-loss-results.md`, Kiyota finding 4). The 7.0 at 2.78 kHz rounds the Fig. 16 ratios (4.95 to 6.96).
   `examples/kiyota_losses_check.py` takes the printed values and subtracts nothing.
2. Table III (2014, p. 5718, read from the page image) prints "Mechanical loss, kW" in its own row: 0.2, 0.7 and
   0.6 kW at (a), (b) and (c). Its efficiencies close only with the mechanical loss outside "iron and other". At (a)
   the input is 60.5 + 6.8 + 0.7 + 0.2 = 68.2 kW, so eta_e = 60.7 / 68.2 = 89.0 % and eta_m = 60.5 / 68.2 = 88.7 %,
   both as printed. At (c), with the 0.6 kW inside "iron and other", eta_e would be 98.3 % against 96.4 % printed.
3. For Fig. 16 the paper says so: "The iron and other losses are given by subtracting the output power, the copper
   loss, and the mechanical loss from the input power" (2014, p. 5719).

So the rated set counts windage and friction once. The windage heat enters the rotor iron after the iron factor
(`thermal_load.py:74`), not under it. Gate V4 also kept `mechanical_loss` in its rated set, so its 573 W is counted
once (`docs/r5-thermal-results.md` left this to D9).

### 8. Shaft power (review issue 11)

The requirement checks compare electromagnetic torque with the required torque: `turns._ratios` uses the envelope
power (map torque x speed) and `check_requirement` asks the stroke for the required torque x the torque factor
(`thermal.py:315`). No iron, windage or friction torque is taken off. The 28 kW at the wheel is set at the shaft by
the caller (28 / 0.93, about 30 kW). That part needs only a docstring.

### 9. Current ripple (review issue 12)

The drive clips the current at the winding's limit with no ripple (`turns._envelope`, `turns._drive_key`). In wire
mode that limit is `phase_current_a`, the 170 A device peak. The ripple depends on the incremental inductance where
the current is chopped, and near alignment at high current that is much lower than Lu:

| Map | Lu (secant, low current) | Lowest L_inc over the angles at the top current | Where |
|---|---|---|---|
| 8/6 screening, 163 A at 20 turns, end winding in | 0.413 mH | 0.096 mH | 0.97 of the pitch from unaligned |
| Kiyota 18/12, 300 A | 1.023 mH | 0.243 mH | aligned |
| 8/6 screening, 30 A at 20 turns | 0.412 mH | 0.416 mH | unaligned (no saturation) |

So Lu under-predicts the ripple by about 4x at the current limit (D7). The ripple also grows with the bus voltage, so
the device peak is reached at the highest bus voltage (420 V per §11 item 12), not at the 300 V design voltage. All
three reference controllers chop soft (`src/srmsil/c/controllers/*/README.md`). The owner's inverter is not chosen.

### 10. Single-pulse preference (owner, 2026-11-27)

Density mode ranks by most equivalent turns (`turns.py:203`). With continuous conduction (PR #44) the 8/6 density case
moved from 242 to 500 turns (`docs/validation/cc86_8_6_density.json`). The envelope already knows each stroke's start
flux (`envelope.py:304`, `psi0`), so the best single-pulse stroke per speed costs one more argmax.

### 11. First bending (step 1)

Probe model: rigid simply supported shaft of the rotor's shaft diameter, rotor laminations lumped at mid-span plus
17/35 of the shaft mass (Rayleigh, not the Dunkerley bound of D10, which reads a little lower), steel_1010 shaft
(E 205 GPa, 7870 kg/m3), span = stack + 2 x (coil build + liner) + 2 x 15 mm. First bending over top speed, stage-1
passing designs:

| Pole set | Ratio 8, below 1.3 | Ratio 15, below 1.3 | Ratio 15, lowest |
|---|---|---|---|
| 6/4 | 0 of 1 | 4 of 9 | 0.68 |
| 8/6 | 2 of 16 | 9 of 27 | 0.63 |
| 12/8 | 0 of 11 | 2 of 20 | 1.05 |
| 24/16 | 0 of 22 | 0 of 36 | 1.34 |

The check binds at ratio 15. Rigid supports read the speed high: ball-bearing compliance is not in the model and has
no cited stiffness here (risk R4).

### 12. Bearing speed (step 1, revised 2026-11-28)

The owner chose three hybrid angular-contact candidates (core spec §11, 2026-11-27; values and sources in
`docs/bearing-candidates.md`). The check blocks a design when 1.2 x top speed is above the candidate's catalogue
limiting speed for its lubrication x 0.81 (SKF Table 39, DB set at preload A; 0.81 assumed for NSK until its factor is
read; §11, 2026-11-28 item 3). Limits x 0.81, r/min:

| Candidate | d x D x B, mm | Grease | Oil-air |
|---|---|---|---|
| SKF 7005 CD/HCP4A | 25 x 47 x 12 | 34 830 | 54 270 |
| NSK 30BNR19HTSUMP3 | 30 x 47 x 9 | 25 920 | 29 970 |
| SKF 7006 CD/HCP4A | 30 x 55 x 13 | 30 780 | 45 360 |

At ratio 15 the check speed is 1.2 x 19 894 = 23 873 r/min, 92 % of the lowest limit (NSK on grease). So every
candidate passes every bike ratio, and the check binds only above a 21 600 r/min top speed. The 2026-11-27 reading of
the Koyo 60 series (6005 at 15 000 r/min on grease, which blocked every shaft of 25 mm and up) is superseded.

### 13. Air-gap closure (step 1)

`rate_context` already computes four `GapClosure` cases (`thermal.py:513-530`), with the centrifugal growth raised by
1 / (1 - 0.094). 10JNEX900 has no expansion coefficient, so `closure` is None. The rating knows the rotor and bore
temperatures. With one material for stator and rotor and the rotor hotter than the bore, the thermal part only adds
closure, so the centrifugal part alone is a valid lower bound to check now (D12).

## Design decisions

- **D1. One home for the hard limits.** `src/srmapp/limits.py` holds `Limit(name, status, value, limit, note)` with
  status `pass`, `fail` or `not_run`, and one function per limit. `hard_limits(req, machine)` returns the four
  closed-form ones (rotor stress, iron frequency, bending, bearing speed). `gap_limit(machine, rating)` runs after a
  rating.
- **D2. Search strict, case as given.** `run_search` rejects a candidate with any `fail`, and with `not_run` for
  `rotor_stress` and `bending` (`SEARCH_REQUIRES_PASS`). So a search never shortlists an unverified rotor or shaft: a
  search on a rotor material without strength data gives no candidates and says why. `evaluate_stage2` makes a design
  infeasible on any `fail` and adds a note for each `not_run`. So M19 and DXF cases still evaluate, and say what was
  not checked. Stress statuses: `ok` with SF >= 1.5 is `pass`. `ok` below 1.5, `kt_out_of_range` and `no_fillet` are
  `fail`. `no_strength_data` and `imported_iron` are `not_run`.
- **D3. Frequency cap before sampling.** A pole set whose top stator electrical frequency is above `K_IRON_HI[-1][0]`
  is removed before sampling, so its share of `n_candidates` goes to the other sets.
  `SearchResult.dropped_pole_sets` names it with the reason. In a case evaluation the same limit is a `fail`.
- **D4. Shortlist order.** Per pole set, the stage-1 passing designs that pass the limits are sorted by
  (`BOUND_SHARE` x `torque_upper` < margin x required torque, `mass.total`): likely designs first, each group
  lightest first. `BOUND_SHARE` is the largest measured drive torque over bound (Task 9 run) x 1.1. This only orders.
  It drops nothing, so stage 1 keeps its no-false-drop contract. The shortlist is filled round-robin over the pole
  sets (each round takes the next design of every set, lightest head first). A set leaves the rotation when it has
  `per_pole_set` feasible evaluations (None: no cap) or no designs left. `shortlist` stays the total evaluation
  budget.
- **D5. Objective.** `SearchResult.recommended()` is the feasible designs with finite rated values, lightest first
  (ties: higher rated continuous kW/kg first). Each evaluation also carries `nominal_continuous_kw_per_kg` and
  `nominal_peak_kw_per_kg` from `rating.nominal`. "Top under both": a lighter design can hold on nominal values and
  fail only the rated set. When no winding of a design holds the rated check, stage 2 runs one more check on the
  nominal set (`check_requirement(..., rows=frozenset())`) and stores it as `Evaluation.nominal_check`.
  `SearchResult.recommendation` is the first recommended design when no lighter evaluated design holds the nominal
  check, else None. `margin_sensitive()` then names the lighter designs, so the owner decides. `pareto()` is
  unchanged and still feeds the web plot.
- **D6. Shaft power.** `Requirements.peak_power_w`, `peak_torque_nm` and `continuous_power_w` are at the motor shaft.
  In `ThermalContext.load_at`, a shaft torque T needs a stroke whose EM torque is at least
  (T + (P_iron x iron factor + P_mech) / omega) x torque factor. The iron loss is the stroke's own (`sl.iron_w`).
  P_mech is the `mechanical_loss` that `load_at` already computes for the set: nominal, or the high end of both bands
  in the rated set (D9 keeps the row). It does not depend on the torque, so compute it once. Start at T x factor.
  While the stroke's `torque_avg` is below that need x (1 - `DRAG_TOL`) (1e-3), solve again at the need (at most
  `DRAG_MAX_STROKES` = 4 strokes, and more raises `RuntimeError`, which the batch boundary turns into a failed
  evaluation). Check and rating both use `load_at`, so rated torques are shaft torques. The EM-only scan stays on EM
  power. With `thermal` off the evaluation notes that the power check has no losses.
- **D7. Ripple.** New `Requirements.switching_frequency_hz` (None: no ripple check, today's behaviour) and
  `max_bus_voltage_v` (None: `bus_voltage_v`). When both `switching_frequency_hz` and `phase_current_a` are set,
  `choose_turns` replaces each winding's current by the largest I <= `w.current` with I + dI(I)/2 <= `phase_current_a`.
  dI(I) = V / (2 L f) is the peak-to-peak ripple of hard chopping at zero back-EMF, V = `max_bus_voltage_v`. L is the
  lowest incremental inductance over the map angles at I on the winding's rescaled map (`l_inc` of the excited
  column, end winding included, NaN skipped). I + dI(I)/2 rises with I, so a 0.1 % grid of [0, `w.current`] finds it on
  the safe side. A winding with no such I is dropped. Hard chopping is the safe side (twice the soft-chopping ripple)
  while the inverter is not chosen (open item). Every later use (scan, thermal, losses, SIL, web) reads the regulated
  `Winding.current`, and a note states the regulated limit, the device peak, f and V.
- **D8. Single pulse first in density mode.** `Envelope.torque_single_pulse` (default None) is the best torque per speed
  over the strokes with start flux 0, after the RMS filter. It is not a new simulation. `ScanPoint.single_pulse`
  (default True) is true when those torques meet the margin at base speed and over the band. The density-mode key
  becomes (not `single_pulse`, -turns / paths, paths). The wire-mode key does not change.
- **D9. Windage in the rated set: dropped (2026-11-28).** Kiyota's "iron and other" leaves the mechanical loss out
  (Diagnosis 7), so `K_IRON_HI` holds no windage or friction. The rated set keeps every row of `ROWS`,
  `mechanical_loss` included, and `check_requirement`, `rate_context` and the budget-share loop do not change (the loop
  keeps `thermal_mesh` and `end_winding_model` at 0 K). No `cooling.RATED_ROWS` is made, so the local `RATED_ROWS` of
  `examples/kiyota_thermal_check.py` (every row except `end_winding_model`) has no name clash. Kiyota names skin effect
  in the winding among the causes of "other". The wire-mode copper model also adds skin and proximity loss, so that
  part may count twice, on the safe side. This plan does not change it.
- **D10. Bending.** First bending speed by Dunkerley (a lower bound of the fundamental): 1/w^2 = 1/w_r^2 + 1/w_s^2,
  w_r^2 = 48 E I / (m_rotor L^3) with the rotor laminations lumped at mid-span, w_s = (pi / L)^2 sqrt(E I / (rho A))
  for the uniform shaft. Rigid simple supports. The stack's added stiffness is left out (safe side) and so is the
  bearing compliance (unsafe side, R4). Limit 1.3 x `max_speed_rpm` (`BENDING_MARGIN`). Span: new
  `BearingSetup.span_m`. None: stack + 2 x (coil build + liner) + 2 x `SPAN_ALLOWANCE` (15 mm, half a bearing width plus
  a wall, a placeholder with a note). A longer span lowers the speed. The allowance is on the safe side only when it
  is at least the real distance from the end winding to the bearing centre. With one candidate per end (half width
  4.5 to 6.5 mm) 15 mm leaves 8.5 to 10.5 mm for clearance and end cap. A DB set per end (half width 9 to 13 mm)
  leaves 2 to 6 mm, which is likely short. The note says so, and the owner's end-cap drawing sets `span_m` (R4).
- **D11. Bearing speed (owner, §11 2026-11-27 and 2026-11-28).** `bearing_limit(req)` is `fail` when
  `OVERSPEED` (1.2, `srmcore.post.rotor_stress`) x `max_speed_rpm` is above the candidate's catalogue limiting speed
  for its lubrication x `DB_PRELOAD_A` (0.81), else `pass`. It never returns `not_run`. New fields
  `BearingSetup.candidate` (one of the three names of Diagnosis 12, or None) and `BearingSetup.lubrication` (`grease`
  or `oil_air`, default `grease`). With `candidate` None the check takes the lowest limit of the three for the
  lubrication, so it holds for whichever candidate the order pack picks (on grease: NSK 30BNR19HTSUMP3, 25 920 r/min,
  so a top speed of at most 21 600 r/min). The candidate is a field. A rule "the smallest bore that fits the shaft"
  was rejected for three reasons. The final choice is open (§11). The shaft diameter is a sampled variable. A journal
  can step down from the rotor seat, so every shaft of 25 mm and up would "fit" the 7005, the fastest candidate, and
  pass designs that the NSK would block. The check does not relate the candidate bore to the shaft (open item 8). The note names the candidate, the
  lubrication, the catalogue speed and the factor, and says when the factor is assumed (NSK). In `hard_limits`, so a
  `fail` rejects a search candidate (D2) and makes a case infeasible.
- **D12. Gap closure.** `gap_limit`: the larger closure of `continuous_overspeed` and `peak_overspeed` must be at most
  0.5 x `air_gap` (`GAP_SHARE`, §11 2026-11-27 item 4). With `closure` None, stator and rotor of one material and the
  rotor at or above the bore temperature in both cases, check the centrifugal part alone (`pass` or `fail`, note: the
  thermal part is not run). Otherwise `not_run`. It never blocks while `not_run` (caller's rule).
- **D13. Total length.** New `Requirements.max_length_m` (stack plus both end windings, as `active_volume`). Stage 1
  rejects above it (after the mass check). The generator's stack range tops at `max_length_m` when set.
- **D14. Thermal errors.** Refusals are `MissingLossData` and `MissingCoolingData` only. Thermal asked but not done
  makes the design infeasible (note "not thermally rated"). The batch boundaries log the traceback
  (`logging.getLogger("srmapp.evaluate").exception`). `choose_turns` errors other than `ScanCancelled` become failed
  evaluations. `run_search` stops after the third evaluation with the same failure status (an exception class name)
  and sets `SearchResult.stopped`.

## Owner decisions this plan follows

- Bearing speed blocks, at the candidate's limit x 0.81 (§11, 2026-11-28 item 3): D11, Task 12.
- The ranking states the peak-rating gap as a band, and the cooling paths and a 30 s peak from warm are checked on the
  winner in the confirm step (§11, 2026-11-28 item 2): Task 10.
- No answer needed to start: the ripple assumes hard chopping at the highest bus voltage (D7). Soft chopping halves
  it. That is one constant once the inverter is known.

## Files

- Create: `src/srmapp/limits.py`, `tests/app/test_limits.py`, `tests/app/test_app_ripple.py`,
  `tests/app/test_app_single_pulse.py`, `tests/app/test_app_shortlist.py`, `tests/app/test_thermal_drag.py`,
  `examples/bound_share.py`,
  `docs/bike-v1-gates-results.md`, `docs/validation/bike_gates_bound_share.json`,
  `docs/validation/bike_gates_rating_screening.json`, `docs/reports/bike-v1-0.md`, `docs/reports/bike-v1-1.md`.
- Modify: `src/srmapp/requirements.py`, `src/srmapp/mechanical.py`, `src/srmapp/sizing/generator.py`,
  `src/srmapp/sizing/stage1.py`, `src/srmapp/pipeline.py`, `src/srmapp/evaluate.py`, `src/srmapp/thermal.py`,
  `src/srmapp/turns.py`, `src/srmapp/drive/envelope.py`, `src/srmapp/__init__.py` (0.12.0),
  `src/srmweb/serialize.py`, `src/srmweb/__init__.py` (0.12.2), `web/openapi.json`, `web/src/api/schema.ts`
  (generated), and the tests named per task. `src/srmapp/cooling.py` does not change (D9).
- Modify docs: `CLAUDE.md`, `docs/r5-sources.md` (new sections 10 and 11), `docs/r3-loss-results.md` (Kiyota finding
  1), `docs/r5-thermal-results.md` (shaft-torque ratings, the V4 mechanical-loss paragraph), the roadmap spec §0 part 0
  wording, `docs/reports/README.md`.

---

### Task 1: `limits.py`, rotor stress gate, yoke floor (about 4 h)

**Files:** `src/srmapp/limits.py`, `src/srmapp/sizing/generator.py:50`, `src/srmapp/pipeline.py`,
`src/srmapp/evaluate.py`, `tests/app/test_limits.py`, `tests/app/test_app_pipeline.py`, `tests/app/test_app_evaluate.py`.

- [ ] `Limit` frozen dataclass (D1). `rotor_limit(machine, req)` calls `rotor_stress(machine, rotor.density,
  rotor.mechanical, req.max_speed_rpm)` and maps the status as D2. Note text names the safety factor, 1.5 and the check
  speed (for example "rotor safety factor 1.32 below 1.5 at 23 873 r/min (1.2 x top speed)").
- [ ] `hard_limits(req, machine)` returns the rotor limit (the others come in Tasks 2, 11 and 12).
  `SEARCH_REQUIRES_PASS = ("rotor_stress",)` for now, with a one-line why.
- [ ] Generator: rotor yoke `w_r * (0.55 + 0.45 * u[6])`, comment: the stress model's box starts at 0.55 of the tip chord.
- [ ] `run_search`: after stage 1, apply `hard_limits` to the passing designs and reject per D2. New fields
  `SearchResult.limit_rejected: dict[str, int] = {}` (rejections per limit name; a candidate that fails several limits
  counts under each). `stage1_rejected` also counts each limit-rejected candidate, once.
- [ ] `evaluate_stage2`: `limits = hard_limits(req, chosen)`. Any `fail` makes it infeasible with its note, each
  `not_run` adds its note. New field `Evaluation.limits: tuple[Limit, ...] = ()`.
- [ ] Tests (fast): status mapping for all five stress statuses (build each with `make_8_6` overrides: 10JNEX900
  rotor, M19 rotor, zero fillet, yoke ratio 0.5, `iron` set), the safety factor equals the one `rotor_stress` gives
  with a rotor temperature (the temperature only adds a note, so the rating's stress and the gate agree), the generator's yoke ratio is in [0.55, 1.0] over 40 samples, a search on an M19 rotor
  rejects every candidate with the reason counted, and an evaluation with a failing rotor is infeasible.
- [ ] Expected literal changes: `test_search_candidates_use_the_settings_materials`
  (`tests/app/test_app_pipeline.py:131`): materials `RegionMaterials()` to `RegionMaterials(rotor="10JNEX900")`
  (M19 stator keeps the 1.12 margin), because the M19 rotor has no strength data and every candidate is now rejected.
  `test_mass_over_the_limit_after_the_winding_is_chosen_is_infeasible` (`tests/app/test_app_evaluate.py:190`):
  `free.error` gains the "rotor stress not checked: the rotor material has no mechanical data" note. Tasks 6 and 13
  add more notes to the same string (thermal off, gap closure with no rating), so the assertion becomes
  `"not thermally rated" in free.error and "rotor stress not checked" in free.error` now, and those tasks leave it.
- [ ] `python -m pytest tests/app/test_limits.py tests/app/test_app_pipeline.py tests/app/test_app_evaluate.py
  tests/app/test_app_generator.py -m "not slow"` passes. Commit.

### Task 2: Pole sets and the iron-loss frequency cap (about 1.5 h)

**Files:** `src/srmapp/sizing/generator.py:19`, `src/srmapp/pipeline.py`, `src/srmapp/limits.py`,
`tests/app/test_limits.py`, `tests/app/test_app_generator.py`.

- [ ] `POLE_SETS` gains `(16, 12, 4)`. Comment: about 64 % of its samples fall outside the stress model's pole arc range
  (12 rotor poles were swept at 3 phases) and are rejected with that reason.
- [ ] `SearchSettings.pole_sets` (default `POLE_SETS`) and `SearchSettings.per_pole_set: int | None = None` (used in
  Task 9).
- [ ] `frequency_limit(n_rotor_poles, req)` (D3): `pass` at or under `K_IRON_HI[-1][0]`, else `fail` with the
  frequency in the note. In `hard_limits`. `run_search` drops failing pole sets before sampling into
  `SearchResult.dropped_pole_sets: dict[str, str] = {}`.
- [ ] Tests: the bike ratios drop 24/16 at 10 610 r/min (2829 Hz) and keep 16/12 there, drop 16/12 at 15 915 r/min,
  keep 12/8 at 19 894 r/min (2653 Hz). A search with every set above the cap samples nothing and names every set.
  `(16, 12, 4)` samples pass the validator and the fit check.
- [ ] Expected literal change: `test_split_is_even_over_pole_sets` (`tests/app/test_app_generator.py:60`)
  `[2, 2, 2, 2]` to `[2, 2, 2, 1, 1]` (five sets).
- [ ] Fast tests of the touched files pass. Commit.

### Task 3: Total length limit (about 1 h, planner addition: §11 2026-11-26 item 11 has no code)

**Files:** `src/srmapp/requirements.py`, `src/srmapp/sizing/stage1.py`, `src/srmapp/sizing/generator.py:38`,
`tests/app/test_app_stage1.py`, `tests/app/test_app_generator.py`.

- [ ] `Requirements.max_length_m: float | None` (gt 0, the same metre window as the OD), docstring: stack plus both end
  windings, the `active_volume` length.
- [ ] Stage 1 rejects a total length above it, after the mass check, with "total length X mm above the Y mm limit".
- [ ] Generator: with `max_length_m` set, the stack runs from 0.25 x OD to min(1.2 x OD, `max_length_m`). Unset: the
  stack mapping is unchanged (same samples, same ids).
- [ ] Tests: the reason and its order, unset gives the same candidates as today, set gives no stack above the limit.
- [ ] Fast tests of the touched files pass. Commit.

### Task 4: Thermal errors (about 2 h)

**Files:** `src/srmapp/evaluate.py`, `src/srmapp/pipeline.py`, `tests/app/test_app_evaluate.py`,
`tests/app/test_app_pipeline.py`.

- [ ] `evaluate.py:165`: catch `(MissingLossData, MissingCoolingData)` only. A refusal sets `feasible` False and keeps
  the note "...; not thermally rated". Docstring and module text say so.
- [ ] Log the traceback at `evaluate.py:124` and `:199` with `logging.getLogger(__name__).exception`, naming the
  candidate id.
- [ ] Wrap `choose_turns` (`evaluate.py:135`): `ScanCancelled` as today, any other `Exception` logged and returned as
  a failed evaluation.
- [ ] `run_search`: count statuses other than "ok", "cancelled" and "no_winding". At the third of one status, stop and
  set `SearchResult.stopped: str = ""` to "stopped after 3 evaluations failed with <status>: <last error>".
- [ ] Tests: an `InputError` from the context is a failed evaluation (status "InputError", infeasible), a refusal is
  infeasible with the note, the traceback reaches `caplog`, a `ValueError` from `choose_turns` is a failed evaluation,
  three `MapFailed` fakes stop the search with partial evaluations, two of each of two types do not stop it.
- [ ] Expected literal change: `test_refusal_keeps_em_choice` (`tests/app/test_app_evaluate.py:373`) becomes
  `test_refusal_is_infeasible`, `e.feasible` to `not e.feasible`.
- [ ] Fast tests of the touched files pass. Commit.

### Task 5: Windage in the rated set (dropped 2026-11-28, D9)

No code change and no commit. The rated set keeps `mechanical_loss` (Diagnosis 7). `thermal.py`, `cooling.py` and
`test_rate_8_6` (`set(ROWS)`, `tests/app/test_thermal_rate.py:58`) stay as they are. The doc edits that record the
evidence are in Task 16. The number stays so that the later task numbers and the review issue map do not move.

### Task 6: Shaft power after losses (about 3 h)

**Files:** `src/srmapp/thermal.py:307-323`, `src/srmapp/requirements.py`, `src/srmapp/evaluate.py`,
`tests/app/test_thermal_drag.py` (create).

- [ ] `load_at` per D6, constants `DRAG_TOL` and `DRAG_MAX_STROKES` with a one-line why each. Zero torque keeps the
  zero load.
- [ ] `Requirements` docstring and field comments: power and torque are at the motor shaft. The caller converts wheel
  power (28 kW / 0.93 for the bike).
- [ ] Evaluation note with `thermal` off: "power check without iron, windage and friction loss (thermal off)".
- [ ] Tests (fast, a fake `stroke` and `stroke_losses` on a `ThermalContext` built with `__new__` and the needed
  attributes, or monkeypatched methods): the stroke asked for covers torque plus loss torque times the factor, the loop
  ends after two strokes when the loss is constant, it raises after 4, the nominal set uses iron factor 1 and the
  nominal mechanical loss, the rated set the high end of the mechanical bands, zero torque solves no stroke.
- [ ] Slow tests that read rated torques keep their bounds: `test_rate_8_6`, `test_check_matches_rating_8_6`,
  `test_rated_choice_8_6`. No literal there changes (they assert relations).
- [ ] Commit.

### Task 7: Current ripple (about 3 h)

**Files:** `src/srmapp/requirements.py`, `src/srmapp/turns.py:140-207`, `src/srmapp/evaluate.py`,
`tests/app/test_app_ripple.py`.

- [ ] `Requirements.switching_frequency_hz: float | None` (gt 0) and `max_bus_voltage_v: float | None` (validator: at
  least `bus_voltage_v`).
- [ ] `turns.ripple_limited(windings, result, machine, req) -> list[Winding]` per D7, applied in `choose_turns` to the
  scanned windings and to `only`. Constant `RIPPLE_HALF_SHARE = 0.25` (dI/2 = V / (4 L f), hard chopping at zero
  back-EMF) with the why. On the reference-turns map, L(I) = k^2 x the lowest `l_inc` over the angles at the
  reference current I x k, with k = `turns_scale(machine, w)`. No incremental inductance at a current (all NaN, or L <= 0) raises `ValueError` (Task 4
  turns it into a failed evaluation).
- [ ] Evaluation note when the limit applies: "current limit X A: the Y A device peak less half the Z A ripple (f kHz,
  V V, hard chopping, lowest L_inc W mH)".
- [ ] Tests on `synthetic_map` with `l_inc` set to the analytic dpsi/di of its excited column (linear: L(theta), tanh:
  L(theta) sech^2): the regulated current plus half the ripple at it is at most the device peak and within 0.2 % of it,
  more turns give a higher regulated current, `max_bus_voltage_v` raises the ripple in proportion, unset
  `switching_frequency_hz` or `phase_current_a` leave every winding unchanged, a zero `l_inc` map raises.
- [ ] No existing literal changes: no test sets `switching_frequency_hz`. `tests/app/test_app_scan_equality.py` passes
  unedited.
- [ ] Commit.

### Task 8: Single pulse first in density mode (about 2.5 h)

**Files:** `src/srmapp/drive/envelope.py:300-332`, `src/srmapp/turns.py:127-137,187-203`,
`tests/app/test_app_single_pulse.py`.

- [ ] `Envelope.torque_single_pulse: np.ndarray | None = None` (D8), filled by `envelope` from the same `_strokes`
  pass. `_drive_summary` returns it as a fifth item. `ScanPoint.single_pulse: bool = True`. Density key per D8.
- [ ] Docstrings: `Envelope`, `ScanPoint`, `choose_turns` (density mode ranks single-pulse windings first until mutual
  coupling under continuous conduction is measured, owner 2026-11-27).
- [ ] Tests:
  - `torque_single_pulse` equals the torque of `envelope` with `_strokes` monkeypatched to the single-pulse pass
    (bit for bit), at the speeds of `tests/app/test_drive_continuous.py`.
  - on the synthetic map at 100 V and 0.1 ohm with a band reaching 40 000 r/min (continuous strokes there, see
    `test_drive_continuous.py`), the highest-turn feasible winding is not single pulse and the chosen one is, with
    the most equivalent turns among the single-pulse ones.
  - with no single-pulse feasible winding the old density order holds.
  - wire mode: `ranked` equals `sorted(feasible, key=(resistance, turns, paths))` on the cases of
    `tests/app/test_app_turns.py`, and `point` is unchanged.
- [ ] Density tests in `tests/app/test_app_turns.py:94-125` pass unedited, or each changed assertion is stated with
  the reason (a top-turns winding that needs continuous conduction).
- [ ] `python -m pytest tests/app -m "not slow"` passes (the `turns`, `evaluate` and `app` CI parts). Record its time
  against main on the same machine. Commit.

### Task 9: Shortlist order (about 2.5 h plus the `gates-bound` run)

**Files:** `examples/bound_share.py`, `src/srmapp/sizing/stage1.py`, `src/srmapp/pipeline.py`,
`tests/app/test_app_shortlist.py`, `docs/validation/bike_gates_bound_share.json`.

- [ ] `examples/bound_share.py [--ratio 12] [--per-set 3] [--workers N] [--cache-dir DIR] [--json PATH]`: bike
  requirement of the Diagnosis at that ratio (`switching_frequency_hz` 20 kHz, `max_bus_voltage_v` 420 V, max length
  0.18 m), `sample_candidates` (seed 0, 200) through stage 1 and `hard_limits`. For the first `per-set` designs of
  each kept pole set by mass: build the screening map at the stage-1 range, then record the drive torque at 50 r/min
  at the map top over `torque_upper`, and for the best density winding of `choose_turns` its regulated current over
  170 A. JSON per design: pole set, OD, stack, mass, share, regulated share, chosen turns, whether single pulse.
- [ ] Run unit `gates-bound` (below). Set `BOUND_SHARE` in `stage1.py` = the largest share x 1.1, comment citing the
  JSON. Stop and report if any share is above 0.9 or below 0.3.
- [ ] `run_search` order per D4. Progress total is the budget `min(shortlist, designs)`.
- [ ] Tests (fakes as in `test_app_pipeline.py`): within a pole set the order is (likely, mass), rounds alternate
  sets, `per_pole_set=1` with an always-feasible fake evaluates one per set, a set with only infeasible fakes runs
  until its list or the budget ends, `shortlist` caps the total.
- [ ] Existing `test_app_pipeline.py` tests pass unedited (they count calls, not designs).
- [ ] Commit.

### Task 10: Objective and nominal beside rated (about 3 h)

**Files:** `src/srmapp/evaluate.py`, `src/srmapp/thermal.py:352`, `src/srmapp/pipeline.py`,
`tests/app/test_app_evaluate.py`, `tests/app/test_app_pipeline.py`.

- [ ] `check_requirement(ctx, n_speeds=6, rows=frozenset(ROWS))` (the default keeps today's rated set; D9).
- [ ] `Evaluation.nominal_continuous_kw_per_kg`, `nominal_peak_kw_per_kg` (NaN default), `nominal_check:
  RequirementCheck | None = None`. `_rated_kw_per_kg` takes the set (`rating.rated` or `rating.nominal`).
- [ ] When no winding holds, run the nominal check on `checks[0]` (rebuild its context when more than one was checked,
  as `rate_failed` does) and store it.
- [ ] `SearchResult.recommended()`, `recommendation` and `margin_sensitive()` per D5.
- [ ] Peak band (owner, §11 2026-11-28 item 2): constant `PEAK_BAND_NOTE` in `pipeline.py`, "peak kW/kg is a band
  from rated to nominal: the peak-heat check (V4) measured one 14 s copper-dominated pulse, so the cooling paths and a
  30 s peak from warm have no measured check (confirm step on the winner)". Property `SearchResult.notes` returns
  `(PEAK_BAND_NOTE,)` when `recommended()` is not empty, else `()`. Nothing else.
- [ ] Tests: recommended order and ties, an infeasible lighter design with a holding nominal check makes
  `recommendation` None and appears in `margin_sensitive()`, one without it leaves the recommendation, a thermal-off
  search recommends nothing and has no notes, a search with a recommendation has the peak-band note, nominal kW/kg
  read `rating.nominal`.
- [ ] Commit.

### Task 11: First bending speed (about 3 h)

**Files:** `src/srmapp/mechanical.py`, `src/srmapp/limits.py`, `tests/app/test_limits.py`, `docs/r5-sources.md`
(new section 10).

- [ ] Source: read one open text that states Dunkerley's formula and the simply supported beam stiffness 48 E I / L^3
  and the uniform-beam first frequency (a university vibration text or a NASA report you can open). Record it in
  `docs/r5-sources.md` section 10 with a grade, the rigid-support and lumped-mass assumptions and their signs.
- [ ] `BearingSetup.span_m: float | None` (gt 0) and `SPAN_ALLOWANCE = 0.015` (placeholder; the note says it may be
  short for a DB set per end, D10). `BearingSetup.placeholder` keeps its meaning, the friction inputs: compare
  `type`, `count`, `bore_diameter_m` and `radial_load_n` with their defaults only, so that setting `span_m` (or, in
  Task 12, `candidate` and `lubrication`) does not drop the friction placeholder note. Test it.
- [ ] `mechanical.first_bending_rpm(machine, bearing)` per D10. `bending_limit(machine, req)`: `pass` at or above
  `BENDING_MARGIN` x top speed, `fail` below, `not_run` without shaft mechanical data. In `hard_limits` and
  `SEARCH_REQUIRES_PASS`.
- [ ] Tests: hand numbers for one machine (write the arithmetic in the test), Dunkerley below both single terms, a longer
  span lowers the speed, the placeholder note appears, `make_8_6` at 6000 r/min passes.
- [ ] Commit.

### Task 12: Bearing speed (about 2 h, revised 2026-11-28)

**Files:** `src/srmapp/mechanical.py`, `src/srmapp/limits.py`, `tests/app/test_limits.py`, `docs/r5-sources.md`
(new section 11).

- [ ] `docs/r5-sources.md` section 11 (core spec §11 2026-11-27 puts the values there): the six catalogue speeds of
  `docs/bearing-candidates.md` with d x D x B and basis (single bearing; SKF "attainable"), SKF Table 39 (DB set
  factors 0.81 / 0.75 / 0.65 / 0.40 for preload A to D), and the SKF note that oil-air values drop for oil mist or
  jet. Grades: SKF B (catalogue values). NSK C (the page is the YN variant, not the exact designation, and its set
  factor is not read, so 0.81 is assumed). Point to `docs/bearing-candidates.md` for the full record. JTEKT's 80 %
  consult rule is not carried over: it is a rule of JTEKT's own catalogue, and the 0.81 set factor takes its place.
- [ ] `mechanical.py`: `BEARING_SPEED_RPM` (candidate name to grease and oil-air catalogue speeds) and
  `DB_PRELOAD_A = 0.81`, each with a source comment. `BearingCandidate = Literal["SKF 7005 CD/HCP4A",
  "NSK 30BNR19HTSUMP3", "SKF 7006 CD/HCP4A"]`. `BearingSetup.candidate: BearingCandidate | None = None` and
  `BearingSetup.lubrication: Literal["grease", "oil_air"] = "grease"`. The friction model does not read them (open
  item 8).
- [ ] `limits.bearing_limit(req)` per D11. In `hard_limits`. Not in `SEARCH_REQUIRES_PASS`, because it never returns
  `not_run`.
- [ ] Tests: with no candidate on grease, top speed 21 590 r/min passes and 21 610 fails (NSK, 25 920 r/min).
  `candidate="SKF 7005 CD/HCP4A"` passes at 29 000 and fails at 29 050 (34 830). `oil_air` uses the oil-air speed
  (7005: 54 270). The NSK note says that its factor is assumed. `make_8_6` at 6000 r/min passes. A search whose top
  speed is above the default limit counts every stage-1 pass in `limit_rejected["bearing_speed"]` and evaluates
  nothing (fakes as in `tests/app/test_app_pipeline.py`).
- [ ] Commit.

### Task 13: Air-gap closure (about 1.5 h)

**Files:** `src/srmapp/limits.py`, `src/srmapp/evaluate.py`, `tests/app/test_limits.py`.

- [ ] `gap_limit(machine, rating)` per D12. `evaluate_stage2` adds it to `Evaluation.limits` after a rating and makes
  the design infeasible on `fail`. No rating: `not_run` with "no rating".
- [ ] Tests with hand-built `Rating.gap` values: full closure pass and fail at 0.5 x gap, the centrifugal-only path
  (same material, rotor hotter) pass and fail, a cooler rotor or two materials give `not_run`, `not_run` never makes a
  design infeasible. `tests/app/test_app_evaluate.py:190` holds unedited after Task 1 (a containment check).
- [ ] Commit.

### Task 14: LattePanda runs (about 1.5 h attended, 1.5 h wall)

Run one at a time. Check every acceptance line before committing.

- [ ] Unit `gates-bound` is run in Task 9 (about 40 min at 8 workers, maps cached in `/home/server/srm-forge/cache-bike`):
  `systemd-run --user --unit=gates-bound --collect -p WorkingDirectory=/home/server/srm-forge-gates
  -E PYTHONPATH=src:tests sh -c '/home/server/srm-forge/.venv/bin/python -u examples/bound_share.py --ratio 12
  --per-set 3 --workers 8 --cache-dir /home/server/srm-forge/cache-bike
  --json docs/validation/bike_gates_bound_share.json > /tmp/gates-bound.log 2>&1'`.
  Acceptance: at least 9 designs over at least 3 pole sets, every share in [0.3, 0.9].
- [ ] Unit `gates-rating` (about 30 min): `examples/rating_timing.py --preset screening --json
  docs/validation/bike_gates_rating_screening.json`, same `systemd-run` form. Record the stroke count and the time
  against `RATING_BUDGET_S["screening"]` (1063 s). If over 1063 / 1.25 s, update the budget to the measured x 1.25 in
  `src/srmweb/cases.py` (srmweb is bumped in Task 15). Run the same command from `/home/server/srm-forge` (main,
  srmapp 0.11.0) first and record its rated continuous and peak torques per speed. Take main's numbers from this run
  only: srmapp 0.11.0 gave the iron a heat capacity and the end winding a peak residual, so the peak ends read 2 to
  3 K cooler on the 8/6 than any 0.10.0 record. Acceptance: rated, and every per-speed change against main is a drop
  that the loss torque explains ((iron x factor + mechanical) / omega x torque factor, from the strokes). A rise, or
  a change over 10 % at any speed: stop and report.
- [ ] Gate counts (under 1 min, no unit): for ratios 8, 12 and 15, 250 samples, the counts per pole set of stage-1
  passes, limit rejections per limit and dropped pole sets, written to `docs/bike-v1-gates-results.md` with the
  command used.
- [ ] Commit the JSONs and any constant change.

### Task 15: Versions, web keys and the API schema (about 1 h)

**Files:** `src/srmapp/__init__.py`, `src/srmweb/serialize.py:97-107`, `src/srmweb/__init__.py`,
`tests/web/test_report_route.py:35`, `web/openapi.json`, `web/src/api/schema.ts`.

- [ ] srmapp 0.11.0 to 0.12.0 (feasibility, rankings, rated torques and winding currents change).
- [ ] `search_result_json` adds `recommended_ids`, `recommendation_id`, `notes`, `stopped`, `limit_rejected` and
  `dropped_pole_sets`. srmweb 0.12.1 to 0.12.2, `tests/web/test_report_route.py:35` takes the new literal. `web/`
  stays 0.12.0 (no UI change). The new `BearingSetup` fields reach the API schema through `Requirements`.
- [ ] `python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api; npm run build; npx vitest run`.
  Old setup files load unchanged (new fields are optional). `python -m pytest tests/web -m "not slow"` passes.
- [ ] Commit.

### Task 16: Docs (about 2.5 h)

- [ ] `docs/bike-v1-gates-results.md`: the Diagnosis tables, the `gates-bound` shares and regulated currents, the
  rating time and stroke count, the gate counts, and the limits of each check against the 10 to 15 % target (the
  rigid-bearing error of bending, the hard-chopping assumption, the centrifugal-only gap).
- [ ] `docs/r5-sources.md` sections 10 and 11 (Tasks 11 and 12).
- [ ] D9 evidence. `docs/r3-loss-results.md`, Kiyota finding 1: one sentence that the measurement leaves the
  mechanical loss out (Table III row and efficiencies, 2014 p. 5719), so `K_IRON_HI` holds no windage or friction.
  `docs/r5-thermal-results.md`: the V4 paragraph that says the 573 W "may be counted twice" now says it is counted
  once, with the same evidence, and one new paragraph on the shaft-torque ratings. Roadmap spec §0 part 0: "fix the
  windage double count" becomes "windage double count checked: none (Kiyota Table III)".
- [ ] `CLAUDE.md`: the srmapp paragraph (limits and the search rule, shortlist order and `BOUND_SHARE`,
  `recommended` and the peak-band note, shaft torque in the rating, the ripple-limited winding current, single pulse
  first in density mode, the new `Requirements` and `BearingSetup` fields, the bearing candidates and their factor),
  the "Current state" line and the versions (srmapp 0.12.0, srmweb 0.12.2).
- [ ] `docs/reports/bike-v1-0.md` and `bike-v1-1.md` from `docs/reports/TEMPLATE.md`, rows in
  `docs/reports/README.md` ("Bike v1, part 0" gates and ranking, "Bike v1, part 1" speed checks). Written after CI is
  green, in the merge session.
- [ ] Commit.

### Task 17: Reviews, PR and CI (about 2 h)

- [ ] Opus final review of the whole branch against this plan (spec and code), fixes by the implementer, a scoped
  re-review of the fixes.
- [ ] Push, open the PR, fast CI green on 3.12 and 3.14 in all four parts, the slow suite dispatched on the branch and
  green. Record each part's time (`turns`, `evaluate`, `app`, `rest`) against the last main run. A part within 10 min
  of its 60 min limit: stop and report.
- [ ] Controller, not this plan's implementers: merge, the Notion project doc (section and dated row), the Notion
  tracker (this item Done only when its "Done when" holds, plus the open items below), the Roadmap rows for parts 0
  and 1.

## LattePanda runs

| Unit | Command | Wall time | Output |
|---|---|---|---|
| `gates-bound` | `examples/bound_share.py --ratio 12 --per-set 3 --workers 8` | about 40 min | `docs/validation/bike_gates_bound_share.json` |
| `gates-rating` | `examples/rating_timing.py --preset screening`, main first, then the branch | about 30 min each | `docs/validation/bike_gates_rating_screening.json` |

## Open items this plan leaves (add to the tracker)

1. The final bearing, its lubrication and its preload (order pack, §11 2026-11-27): until then the bearing-speed check
   takes the lowest limit of the three candidates on grease. The NSK set factor (0.81 assumed) and the page of the
   exact NSK designation are not read.
2. Chopping mode of the owner's inverter: hard chopping is assumed (D7).
3. The 10JNEX900 expansion coefficient: the thermal part of the gap closure is not run.
4. Bearing radial stiffness in the bending check (no cited value): the rigid supports read the speed high (R4).
5. An FE stress sweep of 12-pole rotors at 4 phases, so 16/12 samples are not rejected for their pole arc.
6. The efficiency map on shaft power (it still counts EM power as output).
7. A 10JNEX900 ring test above 2.78 kHz, which would lift the frequency cap (review issue 3).
8. The friction model still takes a deep groove ball bearing at the shaft bore. The candidates are angular contact
   at 25 and 30 mm bores, and no check relates the candidate bore to the shaft (a shaft under 25 mm needs a journal
   above the rotor seat). Update the friction default and add a bore check when the bearing is final.
9. The end-cap distance behind `SPAN_ALLOWANCE` (15 mm): likely short for a DB set per end (D10).

## Out of scope

The bike search command, the search preset default (`full`, review issue 4), the cooling-path check and the 30 s peak
from warm (confirm step on the winner, §11 2026-11-28), FE stress and critical speed (part 8), mutual coupling,
`K_IRON_HI` at high power, the possible double count of AC winding loss inside Kiyota's "other" (D9, safe side), the
current-limit grid of continuous strokes, any web UI change, and any srmcore change.

## Risks

- **R1, bound share sample.** Nine to fifteen designs at one ratio set `BOUND_SHARE`. A design with a higher share is
  ordered late, never dropped. If the budget ends first, it is missed. The 1.1 allowance and the per-set rounds limit
  this.
- **R2, rating time.** The loss torque adds about one stroke solve per asked torque. The rating can take up to about 2x
  longer. Task 14 measures it and updates `RATING_BUDGET_S`.
- **R3, ripple derating.** The lowest L_inc is about 0.23 x Lu at the current limit (Diagnosis 9). At 420 V and 20 kHz
  hard chopping, a low-turn winding can lose 20 to 45 % of its current limit. That moves the winding choice to more
  turns and changes results. It is the physics of the owner's 170 A limit, and the hard-chopping half of it is an
  assumption (open item 2).
- **R4, rigid bearings and the span.** A ball bearing of the bike's size can lower the first bending speed by roughly
  5 to 10 % (uncited estimate). The 1.3 margin covers part of it. The 15 mm span allowance may be short for a DB set
  per end (D10), which also reads the speed high. Part 8 (FE on the finalists) includes the bearings.
- **R5, results change.** Every evaluation from srmapp 0.12.0 can differ: feasibility (limits, refusals), the
  winding (ripple, single pulse), rated torques (loss torque). Stored evaluations keep their numbers. The web shows
  the version.
- **R6, test churn.** The expected literal changes are listed per task. Fast-suite time grows by the new tests only
  (synthetic maps, fakes), most of them in the `app` CI part. The rated slow tests get slower by R2.

## Hours

| Task | Hours |
|---|---|
| 1. Limits, rotor stress, yoke floor | 4 |
| 2. Pole sets, frequency cap | 1.5 |
| 3. Total length | 1 |
| 4. Thermal errors | 2 |
| 5. Windage in the rated set (dropped, D9) | 0 |
| 6. Shaft power after losses | 3 |
| 7. Current ripple | 3 |
| 8. Single pulse first | 2.5 |
| 9. Shortlist order | 2.5 |
| 10. Objective | 3 |
| 11. First bending | 3 |
| 12. Bearing speed (candidates read already) | 2 |
| 13. Gap closure | 1.5 |
| 14. LattePanda runs (3 h wall) | 1.5 attended |
| 15. Versions, web keys, API schema | 1 |
| 16. Docs and reports (plus the D9 evidence) | 3 |
| 17. Reviews, PR, CI | 2 |
| Total | 36.5 attended, about 40.5 elapsed |
