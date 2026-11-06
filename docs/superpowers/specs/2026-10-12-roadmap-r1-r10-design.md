# Roadmap R1–R10 — Design Spec

Status: approved in chat 2026-10-12 (owner). Replaces the sub-project order in the core spec §1.3 and the open v0 steps (v0b-3, the v0 optimiser plan). M1–M5 and v0a/v0b stay as history under their old names. Each R gets its own spec, plan and checklist; this file fixes the order, the scope of each step and the decisions behind them.

## 1. What the owner wants

A tool the owner can run without knowing motor design. They enter requirements and get recommendations for the most power-dense SRM. Then they edit the chosen shape and simulate and tune its control.

- **Inputs:** torque and rpm on the output side of the transmission (wheel or sprocket), plus bus voltage and limits. A ratio field is `auto` (the tool picks the ratio and the motor rpm) or a fixed number; ratio 1 is direct drive and is the same as today's motor-side input. An optional motor rpm cap limits `auto` (bearings, balancing, noise, or simply preference).
- **Objectives:** peak and continuous, each as kW/kg and kW/L (active parts). The axes of the options graph are chosen after the preliminary design.
- **What-ifs:** "if I cool it this much, I get X"; limits on bus voltage and current; linked inputs (P = T·ω).
- **Geometry:** parametric designs, DXF export, edits in external CAD (coil-holder notches, laser-weld V-grooves, lightening holes), then DXF import, solve, and a before/after comparison.
- **Control:** software-in-the-loop. The owner's control code is portable C behind a HAL (grblHAL style). The tool provides a simulated HAL driver (converter, PWM, encoder/resolver, ADC) and a motor model, runs current loops, hysteresis, TSF and HFI, optimises the commutation for low torque ripple, and exports the result for the owner's firmware.
- **UI:** clean and black, Scalar-style, no blue, nothing that looks AI-generated.
- **Next real-world use:** the design tool first (no hardware planned yet), control after.
- **Scope beyond the motor:** motor only. No gearbox or inverter mass models. The ratio recommendation is limited by motor-side limits (§3, R7).

## 2. Review findings that shape the order (2026-10-12)

1. **The label overstates.** "EM-validated" rests on verification (mesh convergence, two in-house solvers, FEMM, which is also 2D). The only measured comparisons are low by more than their stated uncertainty: TEAM 24 static torque −13.1 %, rotor flux −17.2 %; Krishnan 6/4 T_avg −16.9 % at 10 A and −28.5 % at 20 A (stated model uncertainty 3.3–6.3 %). The sign is the same everywhere, so the error is systematic, likely 3D end effects, which grow on short stacks. The power-dense designs are the ones with short stacks, so the error can change rankings. → R1 renames the label; R4 calibrates and checks.
2. **The search is a lottery.** About 24 Latin-hypercube samples in an 8-D box, each mapped at `full` (8/6: 1550 s). The screening-vs-full fidelity rule (core spec: key numbers within 3 %, Spearman ρ ≥ 0.95) allows exploring at `screening` and confirming at `full`. → R7.
3. **One assumed number sets every ranking.** `j_limit` = 20 A/mm² RMS stands in for cooling. Power density scales roughly with it. → R3 and R5 before R7. Until R5, results state the assumed value.
4. **The drive model under-rates high speed.** `srmapp.drive.envelope` requires the phase flux to be zero by the aligned position, so high-speed single-pulse strokes cannot trade a little negative torque for more power. → R3.
5. **Order.** The web steps were built before the physics that decides the answer. This roadmap puts the physics first.

What holds: the 2D solution (solvers agree to ~1e-13, FEMM within 0.1–0.6 %, documented mesh convergence), the layering and tests, cached provenance-stamped maps, graded material data, and choosing turns after the map.

## 3. Roadmap

Order chosen by the owner: physics first, with the DXF round trip early because it is independent of the physics.

### R1 — UI reskin and label rename
- [x] Theme tokens: black, Scalar-style, no blue; light and dark only if the R1 spec keeps both
- [x] Plots themed to match
- [x] Every existing page restyled
- [x] Label "EM-validated" renamed "2D-verified" in the engine, API, UI and docs; `VALIDATED_VERSIONS` and the report keep working
- [x] "Assumes j_limit = N A/mm²" shown on every ranked result until R5
- Done when: the owner signs off on screenshots of every page.

### R2 — DXF round trip
- [x] Export stator and rotor laminations (and coil regions) as DXF with a fixed layer convention
- [x] Import an edited DXF; check closed loops, the air-gap circle, minimum web width; map layers to regions
- [x] Mesh and solve the imported shape with the same engine (moving band, maps, products)
- [x] Before/after comparison: ψ, torque, key numbers, mass
- Done when: export → edit in CAD (notches, V-grooves, holes) → import → map → comparison works end to end on the 8/6.
- Open for the R2 spec: how imported shapes enter the cache identity, and whether coils may be edited or stay parametric.

### R3 — Losses and drive tail
- [x] Copper loss: DC at temperature, AC/proximity estimate, end-turn length
- [x] Iron loss for SRM flux waveforms (unipolar, DC-biased, minor loops) from B(t) per element; 10JNEX900 loss data with provenance and grade
- [x] Drive envelope lets the tail run past aligned and counts the negative torque
- [x] Efficiency map
- [x] Checked against published SRM loss data
- Done when: efficiency at any operating point, compared with a published case and the error reported.
- Status 2026-10-19: built (PR #4, 0.6.0). Materu 6/4 check at `full`: computed iron loss 18-78 % below the measurement, outside the stated uncertainty on 7 of 10 rows; likely cause no manufacturing build factor (not confirmed). See `docs/r3-loss-results.md`.

### R3b — Run report (added 2026-10-18)
- [x] One self-contained HTML file per case (opens offline, can be emailed): inputs, outline, key numbers, map plots, before/after table for DXF cases, losses and efficiency from R3, validation checks and budget, and the flux animation playing inline
- [x] A print layout so the static parts save as PDF from the browser (a PDF cannot play the animation) (2026-10-19, branch r3b-run-report)
- Done when: one click on an evaluated case gives the file, and it renders the same with the server stopped.

Side step before R3 (2026-10-18): UI polish — SRM logo and favicon, motor-shaped loading spinner, job queue panel and step-by-step job progress (spec `2026-10-18-ui-polish-queue-design.md`).

### R4 — End effects
- [x] 3D magnetostatic model (NGSolve) built and checked: cost spike G0, slab against 2D G2, TEAM 24 against measurement G1. G1 failed, so the spot checks across stack-length/diameter ratios were not run
- [ ] Dropped, G1 failed: an end-effect correction (as a function of geometry) calibrated against the 3D runs only; the measured TEAM 24 and Krishnan 6/4 data are a check, never a calibration (owner, 2026-11-03; spec `2026-11-03-r4-end-effects-design.md`)
- [x] The measured gap enters the uncertainty budget (`end_effect` row, `MEASURED_GAP`, 2026-11-05). The largest measured residual, Krishnan Lu (+27.3 % to +45.2 %), is not in the budget: decision 7 leaves Lu out, and it is a tracker item for an owner ruling
- [ ] Dropped, G1 failed: the correction in the key numbers and the ranking-bias measure
- [ ] Dropped, G1 failed: the 3D sweep covers the whole air-gap range the R7 optimiser may choose, down to the smallest allowed gap (owner, 2026-11-04: small gaps are worth their cost)
- Done when: the measured comparisons fall inside the stated uncertainty, or the remaining gap is stated in the budget.

### R5 — Thermal and rotor stress
- [ ] 2D cross-section thermal on the motor mesh, with end-winding and housing-end nodes
- [ ] Cooling knobs: the owner picks edges and gives a heat-transfer coefficient and coolant temperature; range bands (air, water jacket, oil) from cited sources
- [ ] Knobs for stator-to-housing contact and slot fill (copper, insulation, impregnation), with defaults
- [ ] Options: water jacket, oil spray on the end windings, oil in the slot gap between coils; rotor temperature reported (shaft cooling only if it says so)
- [ ] Steady state and the 30 s peak transient
- [ ] Continuous rating; the options graph gets continuous kW/kg and kW/L
- [ ] Analytic rotor stress (spinning disc plus pole root) at max speed × safety factor, as a constraint from here on
- [ ] Ratings replace `j_limit` in the winding choice; iron loss carried as a band (× 2.0) and every budget row stacked worst-case (owner, 2026-11-05; spec `2026-11-05-r5-thermal-stress-design.md`)
- Done when: the peak rating matches the measured Kiyota 2014 coil-end transient within its budget, the solver matches Faiz 2009, the winding model matches Márquez-Fernández 2018, the missing measured continuous case is stated in the budget, and ratings and stress render on an 8/6 and a bench-target case (owner, 2026-11-05: no published SRM with a measured continuous temperature and enough geometry was found).

### R6 — What-if tab
- [ ] Linked inputs: P = T·ω (any two give the third)
- [ ] Sweeps of cooling, bus voltage and current limit on a chosen design (absorbs the planned v0b-3 sweep and design study)

### R6b — Software QA (added 2026-11-04, owner)
- [ ] Whole-repo audit: bugs, untested risky code, error handling, CI health, dead or duplicated code; ranked report with fixes
- [ ] Fix what the report ranks as must-fix, each with a test
- Done when: the report is in `docs/`, the must-fix items are merged with CI green, and the rest are tracker items.

### R6c — Speed report (added 2026-11-04, owner)
- [ ] Measured times for every stage (mesh, 2D solve, map, evaluate, winding scan, losses, SIL, 3D) on the LattePanda, with hot spots profiled
- [ ] Comparison with published timings of other tools (FEMM, Ansys Maxwell, JMAG, Motor-CAD, EMDLAB), at matched accuracy where the sources allow (time to a stated torque error), with sources cited
- Done when: the report is in `docs/` with every number traceable to a run or a cited source.

### R6d — Optimisation research (added 2026-11-04, owner)
- [x] Literature review of SRM design optimisation: algorithms (NSGA-II/III, differential evolution, PSO, surrogate/Bayesian, multi-fidelity), pole-shape and topology optimisation, coil and winding choice; which suit this tool and which are fastest for a given accuracy (`docs/r6d-optimisation-research.md`, 2026-11-06)
- [x] A recommendation of the methods R7's spike compares: funnel, NSGA-II/III (pymoo), GP surrogate with qLogNEHVI (BoTorch); stack length rescaled after the map like turns
- Done when: the review is in `docs/` with cited sources and the R7 spike list follows from it.

### R6e — Web review and polish (added 2026-11-04, owner)
- [ ] UX review of every tab with findings ranked
- [ ] Visual polish from the review
- [ ] 3D motor view in the browser: the 2D outline extruded with coils and end turns, rotatable
- Done when: the review's must-fix items and the 3D view are merged, checked on desktop and at 375 px.

### R7 — Decide for me
- [ ] Spike first: NSGA-III vs surrogate/Bayesian vs the current sample-and-filter funnel, same budget and requirements; pick from the results
- [ ] Explore at `screening`, confirm finalists at `full` (fidelity rule above)
- [ ] Ratio `auto`: push motor rpm up until the owner's optional motor rpm cap, rotor stress, electrical frequency or bus voltage limits it (the tool says which one bound); report the ratio and a stage-count hint (rule of thumb, labelled rough); `fixed` uses the given ratio
- [ ] Air gap as a design variable the optimiser chooses (today `srmapp.sizing.generator` sets it by rule, OD/400 clamped to 0.3–0.8 mm). The limits are user inputs: a minimum buildable gap (machining and assembly) and optionally a maximum; the tool also checks rotor radial growth at max speed (R5 rotor stress) and eccentricity (bearing runout, unbalanced magnetic pull) against the chosen gap and says which limit bound (owner, 2026-11-04)
- [ ] Plain-language recommendations ("pick this because …")
- [ ] Live search view while the search runs (owner, 2026-11-06): the options graph filling in map by map with the front redrawn, the design being mapped (outline and its map grid filling in), the stage-1 funnel counts, where the optimiser looks next, and a ticker of finished designs with their binding limit. Only data the job already makes; a still view under `prefers-reduced-motion`
- Done when: requirements in → ranked recommendations with reasons out, on a stated compute budget.

### R8 — Control SIL
- [x] C HAL interface (read currents, read position, set switches, timers)
- [x] Simulated drivers: asymmetric half-bridge, PWM, dead time
- [x] Simulated sensors: encoder and resolver errors, ADC sampling, noise and quantisation
- [x] Time-domain motor model from the maps (ψ(θ,i), T(θ,i), L_inc for HFI)
- [x] The owner's C code compiled and run inside the simulation; scopes in the UI
- [x] Reference controllers: hysteresis, PWM current, TSF
- Done when: a reference controller runs in the simulation and the same file compiles for a target.

### R9 — Ripple optimisation and export
- [ ] Optimise current profile / TSF against speed, trading ripple against copper loss (and the bus-voltage limit at high speed)
- [ ] Export tuned tables as C headers and the controller code
- Done when: ripple reduction shown in the simulation and the exported code compiles.

### R10 — Fabrication package
- [ ] FE rotor stress and pole-root fatigue
- [ ] Winding spec, lamination DXF, materials, warnings, datasheet
- [ ] The "fabrication-ready" checks of the core spec §8.5
- Done when: one design produces a complete package.

## 4. Decisions (2026-10-12, owner)

- Order: physics first, DXF early (approach 3 of three).
- Losses (iron, copper) before thermal; thermal plan as in R5.
- Inputs: output-side torque and rpm with ratio `auto` or fixed.
- Motor only; no gearbox or inverter mass models.
- NSGA is not assumed; R7 starts with a spike.
- Rotor stress is a safety constraint, not an option.
- End effects are handled before the recommender (R4 before R7).
- Fabrication package added as R10.
- Naming: R1–R10 from now on.

## 5. Where to run each step: laptop or Claude cloud (2026-10-18)

The owner has a US$100 credit for Claude cloud sessions. A cloud session is Ubuntu on 4 vCPU and 16 GB with no GUI; a command stops after 2 minutes by default and a background command after 30 more. The credit buys model work, not compute: a session that waits 40 minutes on a map spends the credit on waiting. So cloud fits work that is mostly writing and reviewing code, with only short test runs; long solves belong on the laptop (61.7 solves/min on 10 workers) or the LattePanda, which run them for free.

| Item | Where | Why |
|---|---|---|
| UI polish (logo, spinner, queue) | Cloud | Pure code and vitest; the visual check stays local |
| R3 copper loss, drive tail | Cloud | Analytic code and fast tests |
| R3 iron loss | Split | Model code and literature digging in the cloud; the check against published loss data runs maps, so locally |
| R3b run report | Cloud | Templates and front-end code |
| R4 end effects | Local | 3D NGSolve runs take hours and need RAM |
| R5 thermal and stress | Split | Solver and UI code in the cloud; calibration runs locally |
| R6 what-if tab | Cloud | Mostly UI; sweeps reuse cached maps |
| R6b software QA | Cloud | Code reading and fixes with fast tests |
| R6c speed report | Split | Timings on the LattePanda; literature comparison anywhere |
| R6d optimisation research | Cloud | Reading and writing only |
| R6e web review and polish | Cloud | UI code; the visual check stays local |
| R7 recommender | Split | Spike code in the cloud; the budgeted comparison runs (many maps) locally |
| R8 control SIL | Cloud | C and Python simulation code with fast tests; the biggest code item, so the best use of the credit |
| R9 ripple optimisation | Split | Optimiser code in the cloud; long optimisation runs locally |
| R10 fabrication package | Cloud | Documents, drawings, checks |
| Validation campaigns, slow suite, benchmarks, FEMM, Onshape | Local | CPU-hours, Windows tools or CAD |

Recommendation: spend the credit on R8 first (largest amount of code, little compute), then R3b, R6 and R10. Run each as a subagent-driven plan in a cloud session started from the plan file, while the laptop runs the long jobs of the current physics step in parallel; the two streams meet on main through pull requests.
