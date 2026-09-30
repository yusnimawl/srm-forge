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

1. **Generator** samples designs in a bounded box: pole set (6/4, 8/6, 12/8, 24/16), stator outer diameter, stack length, pole arcs, turns per pole, yoke thicknesses. Latin-hypercube sampling with a fixed seed. Designs the validator rejects (`InputError`) are dropped and counted.
2. **Mass** from geometry and material densities (active parts: stator and rotor iron, copper).
3. **Stage 1, analytic filter** (milliseconds): magnetic-circuit estimate of peak torque and the voltage limit. Drops designs that miss the requirements by a wide margin. The margin is a parameter; the filter must not drop a design that stage 2 would keep (checked on a sample in tests).
4. **Stage 2, reduced FEM map** on the shortlist: `build_map` with a reduced grid, fewer angles and currents than `screening`, target about 20 s per design. Grid sizes come from the M5a convergence study; until then, chosen by measurement against the `screening` map key numbers.
5. **Drive model** (minimal): from ψ(θ, i) and the bus voltage, the energy-conversion-loop method with ideal commutation and a current limit gives average torque and power against speed, hence the torque-speed envelope. Base speed is where the voltage limit starts to bind.
6. **Score**: peak torque, peak power, mass, power density (kW/kg), torque ripple from the map. Designs that miss a requirement are flagged infeasible, not silently dropped from the plot.
7. **Pareto set** over the chosen objectives, non-dominated sorting.

## 5. Web layer

- **Backend:** FastAPI on localhost. Job runner behind an interface (local process pool now; a hosted runner can replace it). Endpoints: submit requirements, job status/progress (WebSocket), cancel, results, design detail. Results stored as HDF5 maps (reusing the map cache) plus JSON summaries.
- **Frontend:** one plain page with Plotly. A 3D scatter of candidates (default axes: mass, peak power, power density; selectable), colour by pole set, infeasible points greyed. Clicking a point opens the detail view: geometry plot, ψ-i curves, torque map, torque-speed curve, key numbers, warnings and the "unvalidated, peak-only" banner.
- **Layering:** new packages sit above `srmcore` (`sizing`, `drive`, `api`, `web`). `srmcore` does not import them. The `project` placeholder in `srmcore` stays empty unless a later plan needs it.

## 6. Optimisation (second plan)

NSGA-III (a library such as pymoo, an installed-or-approved dependency to be decided in that plan) starts from a picked design and reuses the two-stage evaluation. Population and generation counts are bounded by the per-design cost; at about 20 s per design on this laptop, thousands of evaluations take hours to days, so the plan must budget evaluations and may use a surrogate. Decided when that plan is written.

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
| ~20 s per design is too slow for a useful cloud | measure first; tighten the stage-1 filter; reduce the map grid; revisit the speed options in the parent spec §10 |
| The minimal drive model misstates power | label peak-only and unvalidated; compare with a closed-form case in tests; full model is sub-project #4 |
| Unvalidated engine numbers mislead | banner on every result; M5 follows v0 |
| Analytic filter drops good designs | keep the margin generous; test against stage 2 |

## 9. Open items

- DC-bus voltage per vehicle (default 400 V assumed).
- Third Pareto axis: power density versus torque ripple (the default is power density; selectable).
- Optimisation library and evaluation budget (second plan).
- Exact reduced-grid sizes (measured during the first plan).
