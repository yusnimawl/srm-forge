# R5: thermal ratings and rotor stress

Status: approved by the owner in chat 2026-11-05 (decisions in §2). Roadmap item R5
(`2026-10-12-roadmap-r1-r10-design.md`). Build starts after R4 (`2026-11-03-r4-end-effects-design.md`) merges.
Solver, app and UI code can run in the cloud. Calibration and check runs run on the LattePanda (roadmap §5).
Branch for the build: `r5-thermal` off main.

## 1. Goal

Every ranked result today rests on one assumed number: `j_limit` = 20 A/mm² RMS stands in for cooling (roadmap
§2 finding 3). R5 replaces it with ratings computed from losses, a thermal model and a cooling setup, and adds rotor
stress as a hard constraint.

- **Continuous rating:** per speed, the highest torque whose steady-state winding hot spot stays at or below
  insulation class − 20 K (core spec §8.5).
- **Peak rating:** per speed, the highest torque (at most the EM peak envelope) that the motor holds for the peak
  duration, starting from the continuous steady state at that speed, with the same hot-spot limit.
- **Rotor stress:** safety factor ≥ 1.5 at 1.2 × max speed (core spec §8.5), as a constraint from R5 on.
- **Rotor growth:** gap closure at max speed, centrifugal plus thermal, reported for R7.

**Done when** (replaces the roadmap wording, decision 4):

1. The peak rating reproduces the measured Kiyota 2014 coil-end transient within the check's stated budget (§8, V4).
2. The steady and transient thermal solver reproduces Faiz 2009 with the same inputs (V2).
3. The winding homogenisation reproduces the Márquez-Fernández 2018 values (V3).
4. The missing measured continuous case is stated in the budget and is a tracker item.
5. Ratings and stress render on an evaluated 8/6 10JNEX900 case and on one bench-target candidate (§9).
6. `j_limit` no longer takes part in the winding choice, and the search ranks on rated continuous and peak values.

## 2. Owner decisions (2026-11-05)

1. **Materu iron-loss gap (tracker item 4): open finding, carried as a band.** R3 iron loss is 18–78 % below
   Materu's measurement (`docs/r3-loss-results.md`). R5 does not fit a build factor to it. Every rating is computed
   at the nominal iron loss and at iron × `K_IRON_HI`. The constraint uses the pessimistic value. The UI shows both.
   Measurements check, they never calibrate (the R4 rule).
2. **`K_IRON_HI` = 2.0.** Evidence: Kiyota 2014 Fig. 16 (10JNEX900 0.10 mm, 100 kW, 13 900 r/min, 2.78 kHz) has
   3D FEM iron loss at half the measured "iron and other losses". The Materu Table 4 rows need 1.2–1.8. A new tracker
   item runs the R3 model on Kiyota's measured points (§12). Its result replaces the 2.0, possibly with a
   frequency-dependent factor. Tracker item 9 (`ANGLE_CONVERGENCE_REL`) stays inside the iron row and sharpens it
   when measured.
3. **Ratings replace `j_limit`** (§5). A winding is feasible when its rated continuous torque meets the continuous
   requirement and its rated peak meets the peak requirement. `j_limit` survives only as a wide stage-1 screen.
4. **Validation plan** (§8). No published SRM that this session could check measures a continuous temperature with
   enough geometry to rebuild it. So: peak against Kiyota 2014 (measured), steady and transient solver against
   Faiz 2009 (code to code), winding model against Márquez-Fernández 2018 (measured), and the continuous gap stated.
5. **Default cooling:** water-glycol jacket on the stator outside, coolant inlet 65 °C, insulation class H (180 °C),
   so the hot-spot limit is 160 °C. All three are placeholders the owner sets later, labelled "placeholder cooling"
   in the UI. The jacket h comes from a duct-flow correlation on the jacket geometry and flow, not a fixed number.
6. **Internal oil spray is a full option**, the owner's likely choice (not decided). Spray on the end windings with
   oil inlet temperature and flow as inputs, and optional shaft oil to the rotor. The spray h is a band from cited
   sources. The cooling concept is a new owner-decision tracker item. When it is decided, the search default follows.
   **Decided 2026-11-10 (owner, core spec §11):** both. High load: end spray plus the jacket, the oil cooled into the
   water loop by a 3D-printed heat exchanger, so the oil inlet is the water temperature plus the exchanger's approach
   (an input with a band). Low load: jacket only. The search default stays jacket only until spray has cited oil data.
7. **Rotor strength comes from a cited source or not at all.** Without a cited strength, the stress result reads
   "no strength data" and the search refuses that rotor material. A material flagged brittle in its data is checked
   by maximum principal stress against tensile strength, every other one by von Mises against 0.2 % yield.
   **10JNEX900 is ductile (amended 2026-11-05, owner):** Ou et al. 2021 tested it at a yield strength of 570 MPa,
   "very stable", with fracture only after more than 14 % strain (§4.3). The JFE catalogue's "brittle" (F1E-002-02
   p. 1) describes rolling sheet above 3.5 % Si before the CVD process, not the finished product. The JFE data
   request becomes optional, for grade A.
8. **Rotor growth:** R5 reports gap closure (rotor growth minus stator bore growth, centrifugal plus thermal) at the
   continuous hot point and at the peak end point. R7 owns the limit (minimum running gap, eccentricity) and says
   which limit bound.
9. **Uncertainty: worst-case stack.** The rated value uses every budget row at its unfavourable end (§7), as the EM
   `UncertaintyBudget` does. The UI shows nominal, rated and each row's share.

## 3. Non-goals and anti-goals

Non-goals:

- 3D thermal FE, CFD, or a coolant flow network beyond one bulk node per circuit.
- Temperature-dependent B-H and iron-loss data (R3 §11 stays).
- FE rotor stress and pole-root fatigue: R10. R5 is analytic. A 2D elastic FE is used only as a test reference.
- Thermal stress in the rotor, shaft press fit and bearing life.
- Friction and windage as heat sources (R3 excludes them, and the chip says so).
- Converter losses and converter thermal limits.

Anti-goals (failure even if it "works"):

- Any constant fitted to, or tuned after looking at, a measured case (Kiyota, Márquez-Fernández, Materu).
- An invented material, correlation or contact value. Every number in a default has a cited source with a page, or
  is an owner placeholder labelled as one.
- `j_limit` still shaping a ranking after R5.
- A rating shown without its cooling setup and its budget.
- Old evaluations mixed with rated ones. Evaluations made before R5 show "Not thermally rated".

## 4. Inputs

### 4.1 Requirements (`srmapp.requirements.Requirements`)

New fields, all with defaults so older setup files import unchanged (the setup schema version stays):

| Field | Default | Meaning |
|---|---|---|
| `continuous_power_w` | None | Required continuous power over base to max speed. Below base speed the required torque is `continuous_power_w` / ω_base. None means no continuous check, and the result says so. |
| `peak_duration_s` | 30 | Hold time of the peak rating (core spec §1). |
| `insulation_class` | `"H"` | Sets the hot-spot limit: class temperature − 20 K. Classes F (155 °C) and H (180 °C) at least. |
| `cooling` | `CoolingSetup()` | §4.2. |

`winding_temperature_c` (R3) stays for unrated runs and the losses job. A rating computes the winding temperature
and uses it, so the rated losses no longer read the fixed 120 °C.

### 4.2 Cooling setup (`CoolingSetup`, frozen)

| Knob | Default | Notes |
|---|---|---|
| `jacket` | water-glycol, inlet 65 °C, owner placeholder | Channel geometry and flow in. h from a cited duct correlation (Gnielinski or equal), band from the correlation's stated scatter |
| `end_spray` | off | Oil inlet temperature, flow, nozzle count. h band from cited spray-cooling sources |
| `shaft_oil` | off | Rotor cooled through the shaft bore. h band from cited sources |
| `slot_oil` | off | Coolant channel between adjacent coils in the slot (the Márquez-Fernández concept). h band from cited sources |
| `end_space` | natural convection in the end caps | Cited correlation |
| `housing` | aluminium, thickness from a sizing rule | Material from the library, thickness a knob |
| `stator_housing_contact` | equivalent interface gap from a cited range | Knob with band |
| `slot` | liner (`slot_liner_thickness`), impregnation conductivity, fill factor from the winding | Knobs with bands |

The source and page of every default and band go in `docs/r5-sources.md` before the default is coded.

### 4.3 Material data

The core spec §5 reserves fields for thermal conductivity (in-plane and through-stack), specific heat, Young's
modulus, Poisson's ratio and yield strength. R5 adds them as optional `thermal` and `mechanical` blocks in the
material JSON, each with provenance, grade A/B/C and test temperature, the same pattern as the R3 `loss` block. A
`mechanical` block for a brittle steel carries `tensile_strength` and the flag `brittle`. Then yield is not used.

10JNEX900 has no such data in the repo or in JFE catalogue F1E-002-02 (read 2026-11-05). Published values,
full text read 2026-11-05:

- **Source:** J. Ou, Y. Liu, P. Breining, T. Gietzelt, T. Wunsch, M. Doppelbauer, "Experimental Characterization
  and Feasibility Study on High Mechanical Strength Electrical Steels for High-speed Motors Application", IEEE
  Trans. Ind. Appl. 57(1), 2021, pp. 284–293 (journal details from the HIT Scholar record, article 9237150, DOI
  not yet confirmed). Accepted manuscript read at
  https://publikationen.bibliothek.kit.edu/1000125982/128560422. The tensile tests are their ref. [24]: ICEMS 2019,
  Harbin, pp. 1–4.
- **Tested (Fig. 13 and text):** yield strength 570 MPa, "very stable". Samples "fail at plastic region" and break
  "after the strain is higher than 14 %". Test temperature and cutting method of the samples: read from ref. [24]
  at build. Ultimate tensile strength: only in the Fig. 13 plot, digitised at build if needed.
- **Table I (from their refs. [22], [27], [28], not tested by them):** density 7490 kg/m³, Young's modulus
  200–210 GPa, Poisson's ratio 0.33, yield 570 MPa, thermal conductivity 18.6 W/(m·K), Vickers hardness 200–300,
  maximum operating temperature 150 °C.
- **Second use of 570 MPa:** D. Ma et al., Materials 15(23), 8502, 2022 (no source given for the value).
- **Library entry:** yield 570 MPa at grade B (an independent test, not the owner's lot), E, ν and conductivity at
  grade C (secondary table). The grade allowance lowers the usable strength. Stated gaps: strength at temperature
  (not reported, the rotor runs hot) and the effect of the owner's cutting process.

Optional, for grade A (no longer on the critical path): the owner asks JFE, or tests a sample of the owner's lot.

- Product name JNEX-Core, code number 10JNEX900, 0.10 mm (catalogue p. 9).
- Contact: JFE Steel, Electrical Steel Section, Tokyo, TEL +81-3-3597-4099, or the nearest office (catalogue
  pp. 10–11).
- Requested, at room temperature and at about 150 °C if available: tensile strength, 0.2 % yield if any, elongation,
  Young's modulus and Poisson's ratio in rolling and transverse directions, fatigue strength, thermal conductivity
  in-plane and through-stack, specific heat, thermal expansion coefficient.
- Note for the anneal state (core spec §8.5): the catalogue says stress-relieving anneals are not required
  (p. 3).

Other materials follow the same rule: a cited value at its grade, or decision 7's refusal.

## 5. How ratings replace `j_limit`

| Where | Before R5 | After R5 |
|---|---|---|
| Stage 1 filter | none | `j_limit` as a wide screen, labelled "screen", value from the cooling band. Its false-drop rate is measured (tracker item 11) |
| Winding choice (`turns.choose_turns`) | feasible when RMS density ≤ `j_limit` | feasible when rated continuous ≥ requirement and rated peak ≥ requirement. Same tie rule as today (wire mode lowest resistance, density mode most equivalent turns). Windings are rated best-first and the scan stops at the first feasible one. |
| `j_peak_max` | default 2 × `j_limit` | user cap only, default none. The peak rating replaces it |
| Result chips | "Peak only · assumes j_limit N A/mm²" | "Cooling: jacket, h = …, coolant … °C (placeholder)" and "Iron ×2.0 band". "Not thermally rated" on older evaluations |
| Key numbers | peak only | continuous and peak torque and power per speed (nominal and rated), hot spot and where, rotor temperature, gap closure, rotor safety factor |
| Options graph | peak kW/kg, kW/L | adds continuous kW/kg and kW/L (rated) |

Evaluate gets slower: every rated point needs stroke fields (R3 §5). The owner accepted that cost (decision 3, no
cheaper iron proxy). The stroke cache makes a re-rate with new cooling cheap (§10, R6).

## 6. Thermal model

`srmcore/thermal/` (new subpackage, numpy and scipy only, no solver imports).

### 6.1 Domain

- The 2D cross-section of the static EM mesh (`mesh/static.py`): stator iron, coil sides, slot air, rotor iron,
  shaft. The moving band and the air-gap layers are removed. Element ids of the iron stay those of the EM mesh, so
  R3 per-element losses map one to one.
- The 2D plane is the mid-stack slice. Heat crosses the stack ends through lumped links (§6.2).
- Imported iron (R2 DXF cases) works, because the domain is the mesh, not the parametric outline.

### 6.2 Lumped nodes and links

| Node | Linked to |
|---|---|
| End winding, per coil per end | coil-side area by axial conduction along the wires (copper × fill). End-space air by convection or spray |
| End-space air, per end | end windings, rotor end faces, housing end caps |
| Air-gap air | stator bore and rotor surface edges, h from an SRM air-gap correlation (candidate: Romanazzi and Howey 2015, Nu = 0.181 Ta_m^0.207, CFD-derived, abstract read, full text read at build) with its band |
| Housing ring and end caps | stator outer edge through the contact gap. Coolant through the jacket h. Ambient |
| Coolant, per circuit | bulk node, temperature rise from flow and heat |
| Shaft ends | adiabatic by default (conservative). Bearing path a later knob |

### 6.3 Materials

- Lamination in-plane conductivity in the 2D domain. Through-stack conductivity for the axial links.
- Coil sides: homogenised. Cross-wire conductivity from the Milton correlation (fill factor, impregnation
  conductivity), as used by Márquez-Fernández 2018 eq. (6). Hashin–Shtrikman is the lower check. Along-wire
  conductivity is copper × fill.
- Slot liner as a thin resistive layer from `slot_liner_thickness` and its conductivity.

### 6.4 Heat sources

- Iron: R3 per-element loss (W/m³), stator in the stator frame, rotor averaged over its own period in the rotor
  frame, scaled by 1 (nominal) or `K_IRON_HI` (pessimistic). The cut-edge factor (R3c) applies as in R3.
- Copper DC: per coil side and end winding, ρ(T) at the local temperature. The loss and the temperature are iterated
  to convergence.
- Copper AC (wire mode): R3's skin and proximity loss in the coil sides. End windings carry DC and skin only.
- Friction and windage: none (R3 rule).

### 6.5 Solves

- Steady state: P1 conduction plus the lumped network, one sparse system. The fixed-point loop over ρ(T) and any
  temperature-dependent h ends when the hot spot changes by less than a tolerance set in the plan.
- Transient: implicit time stepping (backward Euler or BDF2) with capacities from density × specific heat. The peak
  transient starts from the continuous steady state at that speed, at the required continuous torque (owner,
  2026-11-10).
- Hot spot: the maximum over coil-side nodes and end-winding nodes, with its location reported.

## 7. Uncertainty budget (worst-case stack, decision 9)

Rows, each with a nominal and an unfavourable end:

| Row | Unfavourable end |
|---|---|
| Iron loss | × `K_IRON_HI` (2.0), angle convergence inside |
| EM torque | current for a rated torque taken at torque × (1 + the larger of 10 % and the EM `UncertaintyBudget` peak-torque total less its measured gap, g / (1 − g) of `MEASURED_GAP`) (owner, 2026-11-06). The gap is left out because the model is low on peak torque in every steady-state measured comparison. The 10 % floor is there because a laminated 12/8 reads FEM high on average torque, by up to 10 % at part current ([Przybylski 2022](https://bibliotekanauki.pl/articles/2042786.pdf), Table 2, two-digit data, one machine). The TEAM 24 current rise also reads high, +1.5 % to +10.2 % at 2.95 to 5.45 A, but that rig is solid steel: the flux diffusion time is 30 to 105 ms against 8 to 31 µs for 0.10 mm 10JNEX900, so it is not carried over. The factor is 1.10 on the 8/6 and on 10JNEX900, where the row alone gives about 1.06. High-speed voltage limits are not covered by this argument: real ψ is above the model, so R5 checks them separately |
| Winding cross-wire conductivity | low end of the homogenisation band |
| Slot liner and impregnation | low conductivity end |
| Stator–housing contact | wide end of the interface gap band |
| Air-gap convection | low end of the correlation band |
| Cooling h (jacket, spray, shaft, slot) | low end of each band |
| Lamination conductivity | low end of the grade-C band around 18.6 W/(m·K) (Ou et al. 2021 Table I) until grade-A data |
| Thermal mesh | measured convergence error (V5) |
| End-winding model | the V4 residual |

All rows push the hot spot the same way, so the rated value is one solve with every row at its unfavourable end.
Each row's share is one solve with that row alone at its end. The UI and run report show nominal, rated and the
shares. The EM label "2D-verified" keeps its meaning. A rating carries no validation label of its own until a
validation campaign covers it.

## 8. Evidence chain and gates

Papers read in full on 2026-11-05 (PDFs supplied by the owner, not copied into the repo, IEEE copyright):

- **Kiyota 2014:** K. Kiyota, T. Kakishima, A. Chiba, "Comparison of Test Result and Design Stage Prediction of
  Switched Reluctance Motor Competitive With 60-kW Rare-Earth PM Motor", IEEE Trans. Ind. Electron. 61(10),
  2014, pp. 5712–5721, doi:10.1109/TIE.2014.2304705.
- **Kiyota 2012:** K. Kiyota, A. Chiba, "Design of Switched Reluctance Motor Competitive to 60-kW IPMSM in
  Third-Generation Hybrid Electric Vehicle", IEEE Trans. Ind. Appl. 48(6), 2012, pp. 2303–2309,
  doi:10.1109/TIA.2012.2227091.
- **Faiz 2009:** J. Faiz, B. Ganji, C. E. Carstensen, K. A. Kasper, R. W. De Doncker, "Temperature Rise Analysis
  of Switched Reluctance Motors Due to Electromagnetic Losses", IEEE Trans. Magn. 45(7), 2009, pp. 2927–2934,
  doi:10.1109/TMAG.2009.2015755.
- **Márquez-Fernández 2018:** F. J. Márquez-Fernández, J. H. J. Potgieter, A. G. Fraser, M. D. McCulloch,
  "Experimental validation of a thermal model for high speed switched reluctance machines for traction
  applications", IEEE Trans. Ind. Appl. 54(4), 2018, pp. 3235–3244, doi:10.1109/TIA.2018.2817182.

What each one gives:

| Case | Measured | Inputs available | Gaps |
|---|---|---|---|
| Kiyota 2014/2012 | Coil-end temperature rise **41 K in 10 s** at maximum power, 7500 r/min, about 140 A RMS (read from Fig. 8). Natural cooling, "forced cooling is not implemented". The authors' 70 K at 18 s is an extrapolation, not a measurement. | 18/12, OD 264 mm, rotor outer radius 91 mm, gap 0.5 mm, stator yoke 15.5 mm, stator pole taper 7.5°, stack 87.25 mm stator and 87.15 mm rotor, coil end 10.5 mm, 10JNEX900 0.10 mm, 20 series turns, 9 parallel 0.9 mm wires, slot fill 56–57 %, measured resistance 97.8 mΩ, 650 V | Pole arcs, rotor yoke and shaft only in the Fig. 7 drawing. Housing not described. 10 s is nearly adiabatic for the copper, so the cooling path is checked only weakly. |
| Faiz 2009 | No temperatures. Losses only: core 25.5 W, copper 21.32 W at 1000 r/min (Table IV). | 8/6, OD 125 mm, gap 0.35 mm, stack 90 mm, all of Table I. Conductivities and capacities of Table II. Equivalent winding conductivity 0.83 W/(m·K). h values (Section V). Inside-air temperature from their network (Fig. 8) | A code-to-code check only. The exact time and inside-air case of Table VI and Fig. 11 are read at build and recorded. |
| Márquez-Fernández 2018 | Steady coil temperatures of DC-heated, water-cooled motorettes at 150, 180 and 200 A. Agreement needed cross-wire conductivity 3.0 W/(m·K) (motorette A, fill 0.37) and 3.85 W/(m·K) (motorette B, fill 0.47), against 2.41 and 3.11 from Milton with 1 W/(m·K) potting. | Fill factors, wire data, potting conductivity range 0.6–1 W/(m·K) | Axial-flux SMC motorette, so it checks the winding sub-model only, not the radial mesh. |

Gates:

| Gate | Check | Pass rule | If it fails |
|---|---|---|---|
| V0 | Read and record: every input of V2–V4 in `docs/r5-sources.md` with page, figure and digitisation error. The Kiyota Fig. 7 geometry read off the drawing | complete before any comparison runs | no comparison runs |
| V1 | Analytic solver checks: slab and annulus with uniform heat (steady), lumped RC step (transient), manufactured solution on the unit square | to solver tolerance, fast tests | bug, fix first |
| V2 | Faiz 2009: their geometry, losses, conductivities, h values and inside-air curve as inputs. Compare with their 2D result (Fig. 10, Table VI, equivalent conductivity) | within the digitisation error plus our thermal-mesh error, both computed | find the input difference and record it. A remaining gap is stated |
| V3 | Márquez-Fernández 2018: our Milton homogenisation with their fill factors and potting conductivity gives their 2.41 and 3.11 W/(m·K). The default cross-wire band covers the measured-agreement values 3.0 and 3.85 | exact for the formula, band covers both | revise the band, not the measured values |
| V4 | Kiyota 2014 peak: rebuild the motor (parametric with taper, or imported iron if the drawing needs it), losses from our R3 model at the Fig. 8 point (copper from the measured RMS current and resistance), natural-cooling setup, 10 s transient from the Fig. 8 start temperature | measured 41 K inside our predicted band. The band includes input rows (pole arcs, rotor yoke, housing) each from a perturbation run, never estimated | the residual becomes the end-winding-model row in every budget (§7) |
| V5 | Thermal mesh convergence on the 8/6 and the Kiyota motor | hot spot change measured from `screening` to `full` to `reference` | the error enters the mesh row |
| V6 | Rotor stress: analytic against a test-only 2D linear-elastic FE of the rotor lamination (8/6 and Kiyota) | pole-root and bore stress within the error the plan sets, the FE converged | revise the analytic model or its stress-concentration factor |

The continuous rating has no measured check. That gap is stated in every rating's budget note and in the results,
and it is a new tracker item (§12).

## 9. Rotor stress and growth

`srmcore/post/rotor_stress.py`, analytic, plain data in and out.

- **Model:** the rotor yoke as a rotating annulus on the shaft (plane stress), loaded at its rim by the centrifugal
  pull of the poles. The pole root carries the pole's centrifugal force over the root section, times a
  stress-concentration factor for the root fillet (`rotor_fillet_radius`) from a cited chart.
- **Speed:** 1.2 × `max_speed_rpm` (core spec §8.5). Safety factor = strength / stress. Brittle: maximum principal
  stress against tensile strength. Ductile: von Mises against 0.2 % yield. Strength at the rated rotor temperature
  when the data give it, else at room temperature with a note.
- **Speed limit:** `stress_speed_limit_rpm`, the highest max speed that keeps the safety factor ≥ 1.5. R7's ratio
  `auto` uses it as one of its named limits.
- **Growth:** radial displacement at the rotor pole tip (disc plus pole elongation) plus α·ΔT·r from the rotor
  temperature, minus the stator bore's α·ΔT·r. Reported as gap closure in mm at the continuous hot point and at the
  peak end point, at max speed and at 1.2 × max speed.
- **Imported rotor iron (DXF):** no analytic stress. The result reads "analytic stress not available for imported
  rotor iron, FE stress is R10".

## 10. What R6, R7 and R10 need from R5

| Step | Needs from R5 |
|---|---|
| R6 what-if | `CoolingSetup` knobs as inputs. A re-rate with new cooling reuses the cached stroke fields and runs only the thermal solves. Bus voltage and current-limit sweeps change the strokes, so they solve new strokes. |
| R7 recommender | Rated continuous and peak kW/kg and kW/L as objectives. Rotor stress as a hard constraint and `stress_speed_limit_rpm` as a named limit for ratio `auto`. Gap closure for the air-gap check. Rankings on rated values only. |
| R10 fabrication | The §8.5 thermal criterion (hot spot ≤ class − 20 K at continuous and peak) checked from R5 output. Stress results with stress-concentration factor, location and material provenance as the input to FE stress and fatigue. 10JNEX900 strength at grade A (JFE data or a test of the owner's lot), with its temperature dependence. |

## 11. Where things go

- `srmcore/thermal/`: domain from the static mesh, P1 conduction and capacity, lumped network, steady and transient
  solves, correlations, homogenisation. Import rule row: `thermal` may import model, materials, mesh. It never
  imports gmsh, skfem, ngsolve or netgen. `tests/test_import_rules.py` gets the row.
- `srmcore/post/rotor_stress.py`: stress, speed limit, growth.
- `srmcore/materials`: optional `thermal` and `mechanical` blocks, validated like `loss`.
- `srmapp/thermal.py`: `rate(...)` returns `Rating` (continuous and peak curves, nominal and rated, hot spot,
  rotor temperature, gap closure, stress, budget rows). Speed grid: base speed plus the R3 efficiency-map speeds.
  Torque per speed by bisection to a tolerance set in the plan. Each torque uses the least-copper stroke (R3) on the
  end-corrected map (R4 decision 5).
- `srmapp/turns.py`, `evaluate.py`: feasibility as in §5. `Evaluation` records `rating` and the versions that made
  it.
- `srmweb`: evaluate steps become queued, mesh, mapping, winding, strokes, thermal, saved, with `eta_s` in
  strokes. A Thermal tab: temperature map at continuous steady state and at the peak end (inferno, °C scale),
  rating curves against speed with the nominal-to-rated band, hot-spot table, stress and growth table, the cooling
  form. The run report (R3b) gets the same section. Options-graph axes for continuous kW/kg and kW/L.
- Docs: `docs/r5-sources.md` (every default and band with source and page, the V0 record),
  `docs/r5-thermal-results.md` (V1–V6 tables, the bench-target demonstration).
- Versions: srmcore, srmapp, srmweb and `web/` take the next minor after R4's. The new srmcore version is not in
  `VALIDATED_VERSIONS` until a validation campaign passes.

Bench-target demonstration (owner, 2026-11-03, a bench value, not a vehicle value, tracker item 2 still open):
400 V DC bus, about 60 kW, about 170 A peak phase current, no paralleled discretes. A 10JNEX900 candidate from the
search at this target is rated and its results go in `docs/r5-thermal-results.md`. Air gaps down to 0.3 mm are
acceptable to the owner, so the gap-closure numbers are reported against 0.3 mm as well.

## 12. New tracker items (added when the spec is approved)

| Item | Where | Done when |
|---|---|---|
| Kiyota 10JNEX900 iron-loss check: R3 model on Kiyota 2014 Table III and Fig. 16 points | LattePanda, after R4 | errors in `docs/r3-loss-results.md`, `K_IRON_HI` revised from them |
| Measured continuous thermal case (owner bench or another paper) | Owner | one continuous rating compared with a measurement |
| Cooling concept (jacket, oil spray, or both) | Owner | decision in core spec §11, search default updated |
| 10JNEX900 grade-A mechanical and thermal data, from JFE or a test of the owner's lot (§4.3), optional | Owner | data in the material library with provenance at grade A |

## 13. Open questions for the owner

None. Decisions 1–9 settled the scope on 2026-11-05.

## 14. Risks

- **10JNEX900 strength at grade B only:** the rotor runs hot and the published yield has no temperature data, so
  the speed limit may be optimistic at temperature. The grade allowance covers part of it. Grade-A data closes it.
- **Worst-case stack too conservative:** rankings stay valid in order, and the row shares show which measurement
  buys back margin.
- **V4 is a weak check of cooling:** 10 s is nearly adiabatic. The continuous gap is stated, not hidden.
- **Evaluate time grows:** many stroke solves per case. Accepted (decision 3). The stroke cache keeps re-rates cheap.
