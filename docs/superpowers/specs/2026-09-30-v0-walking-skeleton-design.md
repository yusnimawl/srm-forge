# v0 Walking Skeleton — Design Spec

Status: approved in chat 2026-09-30 (owner); written spec awaiting review.
Parent spec: `2026-09-28-srm-core-engine-design.md` (sub-project #1, `srmcore`). This spec covers a thin end-to-end path through sub-projects #4 (minimal), #5, #6 (later step), #8 and #9, built on the current engine.

## 1. Purpose

The owner wants a web tool: enter requirements (power, torque, speed range, weight), get many candidate motor configurations as a 3D Pareto plot, pick one, see its simulated result, then optimise from it (NSGA).

`srmcore` (M1–M4) simulates one design. Everything else is unbuilt. v0 builds a rough vertical path so the owner sees a working tool early and so the real needs of the engine (speed, drive model) show up before M5 validation. M5 follows v0.

## 2. Scope

**In v0**
- Requirements form; candidate generator; two-stage evaluation; minimal drive model; Pareto plot; design detail page; local backend with jobs.
- Peak values only (peak torque, peak power).
- Every result is labelled **unvalidated, peak-only**.

**Out of v0**
- Loss and thermal models (#2, #3): no efficiency, no continuous rating.
- Full drive simulation (#4): no controller library, no converter losses.
- Fabrication package (#7), DXF export, "EM-validated" label (needs M5).
- Optimisation runs (step 6 below) start only after the Pareto plot works; they are a second plan.

## 3. Requirements (inputs)

| Input | Unit | Default | Note |
|---|---|---|---|
| Peak power | W | required | |
| Peak torque | N·m | required | |
| Base speed, max speed | rpm | required | inputs to the torque-speed check |
| DC-bus voltage | V | 400 | assumed; the vehicle value is an open item (parent spec §10) |
| Outer diameter limit | m | none | |
| Mass limit | kg | none | active parts |

SI internally; conversion at the UI edge only.

## 4. Pipeline

1. **Generator** samples designs in a bounded box: pole set (6/4, 8/6, 12/8, 24/16), stator outer diameter, stack length, pole arcs, turns per pole, yoke thicknesses. Latin-hypercube sampling with a fixed seed. Designs the validator rejects (`InputError`) are dropped and counted. Peak current is the peak current density (default 20 A/mm², `SearchSettings.j_peak`) times the conductor area; provisional until the thermal model.
2. **Mass** from geometry and material densities (active parts: stator and rotor iron, copper).
3. **Stage 1, analytic filter** (milliseconds): closed-form upper bound on peak torque (saturated pole flux times the peak current, one energy rectangle per stroke) and the mass limit; the voltage limit is left to stage 2. Drops designs that miss the requirements by a wide margin. The margin is a parameter; the filter must not drop a design that stage 2 would keep (checked on a sample in tests).
4. **Stage 2, reduced FEM map** on the shortlist: `build_map` with a reduced grid, fewer angles and currents than `screening`. The default grid is 12 angles x 5 currents, chosen from the grid study against the `screening` map key numbers. Measured cost: one design took about 200 s in a 6-design search (about 93 s for one map alone in the grid study); 24 candidates narrowed to 6 evaluated took about 20 min. The engine speed work (parent spec §10 speed options, pool start-up per design, mesh build per design) is the lever and is not yet done.
5. **Drive model** (minimal): from ψ(θ, i) and the bus voltage, the energy-conversion-loop method with ideal commutation and a current limit gives average torque and power against speed, hence the torque-speed envelope. Base speed is where the voltage limit starts to bind.
6. **Score**: peak torque, peak power, mass, power density (kW/kg), copper-only efficiency at base speed. Designs that miss a requirement are flagged infeasible, not silently dropped from the plot.
7. **Pareto set** over the chosen objectives, non-dominated sorting.

## 5. Web layer

- **Backend:** FastAPI on localhost. Job runner behind an interface (local process pool now; a hosted runner can replace it). Endpoints: submit requirements, job status/progress (WebSocket), cancel, results, design detail. Results stored as HDF5 maps (reusing the map cache) plus JSON summaries.
- **Frontend:** one plain page with Plotly. A 3D scatter of candidates (default axes: mass, peak power, power density; selectable), colour by pole set, infeasible points greyed. Clicking a point opens the detail view: geometry plot, ψ-i curves, torque map, torque-speed curve, key numbers, warnings and the "unvalidated, peak-only" banner.
- **Layering:** the package is `srmapp` (`requirements`, `sizing`, `drive`, `evaluate`, `pareto`, `pipeline`), with the web layer to follow in plan v0b. It sits above `srmcore`. `srmcore` does not import them. The `project` placeholder in `srmcore` stays empty unless a later plan needs it.

## 6. Optimisation (second plan)

NSGA-III (a library such as pymoo, an installed-or-approved dependency to be decided in that plan) starts from a picked design and reuses the two-stage evaluation. Population and generation counts are bounded by the per-design cost; at about 200 s per design on this laptop, thousands of evaluations take hours to days, so the plan must budget evaluations and may use a surrogate. Decided when that plan is written.

## 7. Testing

- Generator: determinism for a seed; every kept design passes the validator.
- Stage 1: no false drops on a sample checked against stage 2.
- Drive model: on a linear synthetic map, the torque-speed envelope matches a closed-form result; power = torque × speed.
- Pareto: non-dominated sorting on synthetic points.
- API: job lifecycle, cancel, and a small end-to-end run on one pole set with a tiny grid (marked slow).
- Frontend: smoke test that the page loads and plots a fixed result file.

## 8. Risks

| Risk | Handling |
|---|---|
| About 200 s per design makes a search or an optimisation take hours (24 candidates -> 6 evaluated took about 20 min) | engine speed work is the lever (parent spec §10 speed options, pool start-up per design, mesh build per design), not yet done; also tighten the stage-1 filter and reduce the map grid |
| The minimal drive model misstates power | label peak-only and unvalidated; compare with a closed-form case in tests; full model is sub-project #4 |
| Unvalidated engine numbers mislead | banner on every result; M5 follows v0 |
| Analytic filter drops good designs | keep the margin generous; test against stage 2 |

## 9. Open items

- DC-bus voltage per vehicle (default 400 V assumed).
- Pareto axes are mass, power density and copper-only efficiency at base speed; torque ripple is not computed in v0.
- No feasible design was found for 10 kW / 32 N.m / 3000-9000 rpm / 400 V at 20 A/mm2 in the first 6 evaluated designs (torque ratios 0.02-1.82, power ratios 0.01-0.56). Cause not yet diagnosed; candidates: turns choice vs the 400 V constant-power range, stage-1 bound optimistic, drive model single-pulse only.
- Optimisation library and evaluation budget (second plan).
- Reduced-grid sizes are set (12 x 5) from the grid study; revisit after M5.
