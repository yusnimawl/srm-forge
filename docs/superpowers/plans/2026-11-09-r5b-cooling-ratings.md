# R5b: Cooling, Thermal Network and Ratings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the R5a thermal core into continuous and peak ratings of an evaluated case: cited cooling correlations, the winding homogenisation (gate V3), a `CoolingSetup`, the end-winding and housing network, losses as heat sources, and `srmapp.thermal.rate` with its worst-case budget.

**Architecture:** `srmcore/thermal/` gains two pure-function modules (correlations and homogenisation, numpy only). `srmapp/cooling.py` holds the user-facing `CoolingSetup` and turns it plus a budget-end choice into numbers. `srmapp/thermal_network.py` builds a `ThermalProblem` from the static mesh, the winding and those numbers. `srmapp/thermal.py` finds the rated torques by root finding on the hot spot, each torque using the R3 least-copper stroke and its cached stroke fields. The winding choice is not touched: R5c makes ratings replace `j_limit`.

**Tech Stack:** Python 3.12+, numpy, scipy, pydantic.

**Spec:** `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md` (§2 decisions 1, 2, 5, 6, 8, 9; §4.1, §4.2; §6.2 to §6.5; §7; §8 V3; §11 `srmapp/thermal.py`). R5a plan: `docs/superpowers/plans/2026-11-07-r5a-thermal-stress-core.md` (stage table). R5a carry-overs: `docs/r5-thermal-results.md`, "Open for R5b".

**Branch:** `r5-thermal`, now level with main. One PR for R5b.

## Global Constraints

- SI inside. Temperatures in °C, names ending `_c`. Heat transfer coefficients in W/(m²·K).
- `thermal` may import `model`, `materials`, `mesh` only, never gmsh, skfem, ngsolve or netgen. `srmapp` may import `srmcore` public modules; `srmcore` never imports `srmapp`.
- Anti-goal (spec §3): no invented correlation, material or contact value. Every default and band has a source with page in `docs/r5-sources.md` **before** it is coded, or it is an owner placeholder whose name or note says "placeholder". A cooling option with no cited h band is refused with a message naming the missing source, never given a guessed one.
- No measured case is used to fit or tune anything (Kiyota, Márquez-Fernández, Materu). V3 checks the formula; it never sets a value.
- `K_IRON_HI = 2.0` (decision 2). Hot-spot limit = insulation class temperature − 20 K; class B 130, F 155, H 180 °C.
- Default cooling (decision 5): water-glycol jacket, inlet 65 °C, class H. All three are placeholders.
- EM torque row (spec §7): torque factor = 1 + max(0.10, `budget.total["peak_torque"]` − g/(1 − g)), g = `MEASURED_GAP["peak_torque"]` (0.192), from `srmcore.maps.validation`.
- No version bump in R5b (it comes once, in R5c). No web changes (R5d). `j_limit` keeps choosing the winding until R5c.
- The four papers are at `/home/server/srm-forge/docs/sources/papers/`, git-ignored, IEEE copyright: never `git add` anything under `docs/sources/papers/`. Read them with `python -I` from a scratch directory.
- Test file basenames unique across `tests/`. Comments describe the code as it is. Run tests with `PYTHONPATH=src /home/server/srm-forge/.venv/bin/python -m pytest` (the venv's editable install points at the main checkout).

## Calls made in this plan (not in the spec)

1. **Front and rear ends are identical** (no fan, no axial flow), so the network has one end-space lump and one end-winding lump per coil, with both ends' areas and conductances summed. The hot spot is unchanged by the merge.
2. **Axial link of a coil side to its end winding:** an `AreaLink` on the coil side's elements with g = k_along / (L_stack/2 + l_end/2), where k_along = k_copper × fill and l_end = (mean turn length − 2 L_stack)/2 is one end's length. The 1D rod with distributed heat is lumped, so its residual belongs to the end-winding-model row (filled by V4 in R5e).
3. **Liner band conductivity** (R5a carry-over: the classified band is wider than the liner). Each liner element gets k_band = k_liner × w_band / t_liner, where w_band = liner area / length of the coil boundary facing the liner and t_liner = `slot_liner_thickness`. So the band's through-thickness conductance equals that of the real liner. Tested by a fixed-temperature solve.
4. **Coolant bulk node:** fixed inlet lump plus a free bulk lump joined by a `LumpLink` of 2·ṁ·c_p, so the bulk lump sits at the mean of inlet and outlet. Coolant properties are taken at the inlet temperature.
5. **Stroke resistance:** the rating's strokes use the winding resistance at the hot-spot limit temperature. At the rated torque the winding sits at that limit, and a higher resistance needs more volts, the conservative side.
6. **AC copper with temperature:** R3's skin and proximity excess losses are computed once per stroke at the requirement's `winding_temperature_c`, then scaled by ρ(T_ref)/ρ(T) per region (both terms ∝ 1/ρ while the strand diameter is well below the skin depth). Skin goes to coil sides and end windings by length share, proximity to the coil sides only. Checked against a recompute at another temperature.
7. **Iron capacity:** 10JNEX900 has no cited specific heat, so the stator and rotor iron carry zero capacity. With less mass the transient rises faster: the conservative sign. The rating notes say so.
8. **Transient step check** (R5a carry-over): the peak transient starts at 50 steps and doubles until the end hot spot changes by less than 0.1 K (cap 3200 steps). The step count goes in the result.
9. **Root finding:** torque per speed by the Illinois method on hot spot − limit, bracket [0, envelope torque]. It stops when the bracket is under 1 % of the envelope torque or |hot spot − limit| < 0.5 K, with at most 12 evaluations. `ThermalRunaway` counts as above the limit.
10. **Budget shares** are hot-spot rises, not torque losses: at each speed's rated continuous torque, the hot spot with all rows nominal, with each row alone at its unfavourable end, and with all rows unfavourable. That costs thermal solves only. A share in torque would need one root find per row.
11. **Rows with no measurement yet:** `thermal_mesh` (V5) and `end_winding_model` (V4) are R5e. Until then they have zero width and the rating's notes say "not yet measured (R5e)". The rating carries no validation label (spec §7).
12. **Lamination conductivity band:** from Task 1's sources. If no cited scatter exists, the row uses the grade-C property allowance already used for loss data, 25 % (`srmapp.losses.LOSS_GRADE_ALLOWANCE["C"]`), and says so.
13. **Gap closure:** the centrifugal growth reads up to 9.4 % low against the FE (R5a V6), so the unfavourable end divides it by (1 − 0.094). Reported at max speed and at 1.2 × max speed, at the max-speed continuous state and peak end.
14. **Without an EM budget** (no `validate` run), the EM torque row uses the 10 % floor and the notes say the budget was not computed.

## Review Focus

1. **A cooling option with no cited band** (spray, shaft oil or slot oil not found in Task 1). A person expects a refusal naming the missing source, not a rating on a guessed h. Test in Task 3.
2. **No steady state at any torque** (coolant inlet above the limit, or runaway at zero torque). A person expects a rating of 0 with a note, not an exception or a bisection that returns the bracket end. Test in Task 6.
3. **The envelope cannot reach a bisection torque** (`min_copper_stroke` returns None, e.g. at high speed). That torque is infeasible, not an error. Test in Task 6.
4. **Old setup files and cases** without the new requirement fields must load unchanged with the defaults. Test in Task 3.
5. **Density mode** (no wire): no AC loss, the network still builds, and the notes say AC copper is not computed. Test in Task 5.

---

### Task 1: Cooling sources and the V3 record

**Files:**
- Modify: `docs/r5-sources.md` (new sections 6 to 8 and summary rows)

**Interfaces:**
- Produces: for every item below, the value or formula, its stated scatter or validity range, source, page or equation, and grade, or "not found". Tasks 2 and 3 code only what this task records. Section numbers: 6 correlations and properties, 7 bands, 8 V3 record.

- [ ] **Step 1: Find and record, from primary sources (paper, standard or data sheet with page):**
  - Forced convection in a duct: Gnielinski (turbulent, with its validity range and stated scatter) and the laminar fully developed Nu for the jacket channel shape. Friction factor used inside Gnielinski.
  - Air-gap convection between a rotating salient rotor and a smooth stator: Romanazzi and Howey 2015 (Nu = 0.181 Ta_m^0.207, read the full text for the Taylor-number definition, validity range and band), or an equal cited correlation. Below the critical Taylor number, conduction across the gap.
  - Natural convection in the end space and on the outer housing: a cited correlation or a cited h range.
  - Oil spray on end windings: a cited h range with its oil, flow and nozzle conditions. Shaft oil cooling: cited h range. Slot oil channel (Márquez-Fernández 2018 concept): cited h or the paper's own values.
  - Stator–housing contact: an equivalent interface gap range (cited, with the fit type).
  - Slot liner (Nomex or equal) conductivity and impregnation resin conductivity, each with a range.
  - Aluminium housing alloy conductivity. Copper axial conductivity is in section 2 already.
  - Coolants: 50/50 water–ethylene glycol and one automatic transmission fluid or motor oil: density, specific heat, conductivity, viscosity at 65 °C (and 40 to 100 °C if the source tabulates it).
  - Cross-wire winding conductivity: the Milton correlation exactly as Márquez-Fernández 2018 eq. (6) writes it, the Hashin–Shtrikman lower bound, and the default band for the cross-wire row.
  - Lamination conductivity scatter around 18.6 W/(m·K), if any source gives one (call 12 otherwise).
- [ ] **Step 2: Record V3's inputs** from Márquez-Fernández 2018 (local PDF, read with `python -I` from a scratch directory): fill factors 0.37 and 0.47, wire data, potting conductivity range 0.6 to 1 W/(m·K), the Milton values 2.41 and 3.11 W/(m·K) at 1 W/(m·K), the measured-agreement values 3.0 and 3.85 W/(m·K), each with page and equation or table.
- [ ] **Step 3: Record the owner placeholders** of the default setup: jacket channel height, width, number of passes and flow, housing thickness, inlet 65 °C, class H. Each placeholder is named as one, with no source column.
- [ ] **Step 4: Commit**

```bash
git add docs/r5-sources.md
git commit -m "R5b: cooling sources, bands and the V3 record"
```

### Task 2: Correlations and winding homogenisation (gate V3)

**Files:**
- Create: `src/srmcore/thermal/correlations.py`, `src/srmcore/thermal/homogenise.py`
- Test: `tests/thermal/test_thermal_correlations.py`, `tests/thermal/test_thermal_homogenise.py`

**Interfaces:**
- Consumes: the formulas of `docs/r5-sources.md` sections 6 and 8.
- Produces:
  - `Fluid` (frozen dataclass: `density`, `specific_heat`, `conductivity`, `viscosity`, `name`) and `fluid(name: str, temperature_c: float) -> Fluid` for `"water_glycol_50"` and the oil Task 1 found, interpolated in the cited table, `ValueError` outside it.
  - `duct_h(fluid: Fluid, hydraulic_diameter: float, velocity: float, length: float) -> float`: laminar below Re 2300, Gnielinski in its stated range, `ValueError` outside every range.
  - `airgap_h(gap: float, rotor_radius: float, rpm: float, air_temperature_c: float) -> float`: the Task 1 air-gap correlation, conduction (k_air / gap) below the critical Taylor number.
  - `natural_h(...)`: the Task 1 end-space or housing correlation, signature by its inputs.
  - `milton_k(fill: float, k_copper: float, k_matrix: float) -> float` and `hashin_shtrikman_lower(fill: float, k_copper: float, k_matrix: float) -> float`, both W/(m·K).

- [ ] **Step 1: Write the failing tests**

```python
def test_v3_milton_motorette_a(): assert milton_k(0.37, K_CU, 1.0) == pytest.approx(2.41, abs=0.005)
def test_v3_milton_motorette_b(): assert milton_k(0.47, K_CU, 1.0) == pytest.approx(3.11, abs=0.005)
def test_hs_lower_below_milton(): ...    # fills 0.3..0.6, matrix 0.2..1.0: HS lower <= Milton
def test_duct_laminar_limit(): ...       # Re 1000: Nu equals the cited laminar value for the channel shape
def test_gnielinski_published_point(): ...   # one worked value from the cited source, to its printed digits
def test_duct_out_of_range(): ...        # Re past the cited upper limit -> ValueError
def test_airgap_conduction_below_critical(): ...   # rpm 1 -> k_air / gap
def test_airgap_correlation_point(): ...  # one Ta_m in range -> the cited formula by hand
def test_fluid_table_point(): ...         # a tabulated temperature returns the table row exactly
```
`K_CU` is the copper conductivity Márquez-Fernández used (Task 1 record); if they used none, 391.1 from `docs/r5-sources.md` section 2, and the record says which. If the 2.41 and 3.11 are not reproduced to the printed digits, the gate fails: find the formula difference, record it in `docs/r5-thermal-results.md`, change nothing to make it match.

- [ ] **Step 2: Run, expect import errors.** `PYTHONPATH=src /home/server/srm-forge/.venv/bin/python -m pytest tests/thermal/test_thermal_correlations.py tests/thermal/test_thermal_homogenise.py -v`
- [ ] **Step 3: Implement both modules.** Every function's docstring names its `docs/r5-sources.md` section.
- [ ] **Step 4: Run the tests and `tests/test_import_rules.py`, expect PASS.**
- [ ] **Step 5: Commit** `git commit -m "R5b: cooling correlations and winding homogenisation (V3)"`

### Task 3: `CoolingSetup`, bands and requirement fields

**Files:**
- Create: `src/srmapp/cooling.py`
- Modify: `src/srmapp/requirements.py`
- Test: `tests/app/test_cooling.py`, `tests/app/test_requirements.py` (add)

**Interfaces:**
- Consumes: Task 2 correlations; `docs/r5-sources.md` sections 6 and 7.
- Produces:
  - Pydantic, frozen, `extra="forbid"`: `Jacket` (channel height, width, passes, flow m³/s, inlet °C, coolant name; defaults the Task 1 placeholders), `EndSpray`, `ShaftOil`, `SlotOil` (each with inlet °C, flow, and its geometry knobs), `CoolingSetup` with `jacket: Jacket | None = Jacket()`, `end_spray: EndSpray | None = None`, `shaft_oil: ShaftOil | None = None`, `slot_oil: SlotOil | None = None`, `housing_thickness`, `ambient_c`, `impregnation_conductivity: float | None = None` (None = the cited nominal), `contact_gap: float | None = None`, and `placeholder: bool` (true while any default placeholder is in use).
  - `ROWS = ("iron", "em_torque", "cross_wire", "liner", "contact", "air_gap", "cooling_h", "lamination_k", "thermal_mesh", "end_winding_model")`.
  - `Coefficients` (frozen dataclass): every number the network needs (k values, h values, contact gap, coolant flows and properties, iron factor, torque factor), plus `notes: tuple[str, ...]`.
  - `coefficients(setup: CoolingSetup, machine: RadialSRMParams, rpm: float, unfavourable: frozenset[str], em_torque_total: float | None) -> Coefficients`. A row in `unfavourable` takes its unfavourable end (spec §7 table), every other row its nominal.
  - `MissingCoolingData(ValueError)`: raised for an enabled option whose band Task 1 did not find, naming the option and saying no cited source was found.
  - `Requirements` new fields: `continuous_power_w: float | None = None` (gt 0), `peak_duration_s: float = 30.0` (gt 0), `insulation_class: Literal["B", "F", "H"] = "H"`, `cooling: CoolingSetup = CoolingSetup()`; property `hot_spot_limit_c` (class − 20).

- [ ] **Step 1: Write the failing tests**

```python
def test_default_is_placeholder_jacket(): ...   # CoolingSetup().placeholder and jacket inlet 65
def test_limit_by_class(): ...                  # B 110, F 135, H 160
def test_old_requirements_load(): ...           # a dict without the new fields validates; defaults applied
def test_old_setup_file_imports(): ...          # an existing *.srm-setup.json fixture imports unchanged
def test_each_row_moves_its_number(): ...       # for each row: unfavourable differs from nominal in the documented direction
def test_iron_row_is_k_iron_hi(): ...           # iron factor 1.0 nominal, 2.0 unfavourable
def test_em_torque_floor(): ...                 # em_torque_total None -> 1.10; 0.04 -> 1.10; 0.15 -> 1.15
def test_uncited_option_refused(): ...          # only if Task 1 left one option without a band: MissingCoolingData names it
def test_airgap_h_depends_on_rpm(): ...
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Constants carry a comment with their `docs/r5-sources.md` section.
- [ ] **Step 4: Run `tests/app` and `tests/web` (requirements are in web schemas), expect PASS.**
- [ ] **Step 5: Commit** `git commit -m "R5b: CoolingSetup, budget-row ends and requirement fields"`

### Task 4: Thermal network

**Files:**
- Create: `src/srmapp/thermal_network.py`
- Test: `tests/app/test_thermal_network.py`

**Interfaces:**
- Consumes: `srmcore.thermal` (`thermal_domain`, `ThermalProblem`, `Lump`, links), `Coefficients` (Task 3), `srmapp.sizing.winding.Winding`, `srmapp.sizing.estimates.mean_turn_length`, `coil_side_area`.
- Produces:
  - `Network` (frozen dataclass): `problem: ThermalProblem`, `end_lumps: dict[str, str]` (coil name to its end-winding lump), `coil_of_side: dict[str, str]` (coil side region to coil), `active_share: float` (2 L_stack / mean turn length), `notes`.
  - `build_network(domain: ThermalDomain, machine: RadialSRMParams, winding: Winding, fill: float, coeffs: Coefficients) -> Network`.
  - Lumps: `end_<coil>` (hot_spot, capacity copper + resin), `end_space`, `airgap`, `housing`, `end_caps`, `ambient` (fixed), `coolant_in` (fixed) and `coolant`, plus `oil_in` and `oil` when an oil option is on.
  - Links (spec §6.2 with calls 1 to 4): coil side to `end_<coil>` (call 2); `end_<coil>` to `end_space` (natural, or spray h when `end_spray` is on, then to `oil`); `end_space` to rotor and stator end faces (`AreaLink`, both ends) and to `end_caps`; bore and rotor edges to `airgap` (`EdgeLink`, `airgap_h`); `airgap` to `end_space` through the gap's annular area; outer edges to `housing` (contact gap); `housing` to `coolant` (jacket h over the wetted area, wall conduction in series) and to `end_caps`; `end_caps` to `ambient`; `coolant_in`–`coolant` (call 4); shaft oil and slot oil as in their Task 1 records. Shaft ends adiabatic.
  - Element arrays: iron in-plane conductivity from the material `thermal` block (refuse with a message if missing), coil cross-wire `coeffs.cross_wire`, liner (call 3), air elements the air conductivity, shaft from `steel_1010`. Capacity: copper and resin by fill for coils, shaft from its block, iron zero when the specific heat is missing (call 7).

- [ ] **Step 1: Write the failing tests** (8/6 `screening` from `conftest.make_8_6`)

```python
def test_every_part_anchored(): ...       # ThermalSolver(network.problem).steady(zero load) returns coolant temperature everywhere
def test_energy_balance(): ...           # uniform coil load: heat_to_fixed sums to the input within 1e-9 relative
def test_liner_conductance(): ...        # coil fixed 100, iron fixed 0 via a test-only problem: heat flux equals k_liner * L_face * depth / t within 5 %
def test_coolant_mean_rise(): ...        # coolant lump - inlet == Q / (2 m cp)
def test_end_lump_per_coil(): ...        # n_stator_poles end lumps, each hot_spot
def test_missing_thermal_block_refused(): ...
def test_imported_iron_builds(): ...     # a DXF-style design with stator_hole_air builds
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `git commit -m "R5b: thermal network for a cooling setup"`

### Task 5: Heat sources from a stroke

**Files:**
- Modify: `src/srmapp/losses.py` (`_Side` keeps per-element total W after the cut-edge multiplier: `element_w: np.ndarray`), `src/srmapp/copper.py` (`ac_copper_parts(...) -> tuple[float, float] | None`, skin and proximity; `ac_copper_loss` returns their sum, unchanged values)
- Create: `src/srmapp/thermal_load.py`
- Test: `tests/app/test_thermal_load.py`, `tests/app/test_copper.py` (add)

**Interfaces:**
- Consumes: `StrokeLoss` (`stroke_losses`), `StrokeTrace`, `Network`, `ThermalDomain.from_em`, `Coefficients.iron_factor`.
- Produces:
  - `PointHeat` (frozen dataclass): `iron_w_per_m3: np.ndarray` (thermal element order, × iron factor), `i_rms: float`, `skin_ref_w: float`, `prox_ref_w: float`, `t_ref_c: float`.
  - `point_heat(stroke: StrokeLoss, trace: StrokeTrace, domain, static, winding, wire, machine, t_ref_c, iron_factor) -> PointHeat`. The iron element order of `IronWaveforms` is the iron elements of each static part (`region_kind == "stator_iron"`/`"rotor_iron"`); map it to EM element indices, then `domain.from_em`.
  - `load_fn(heat: PointHeat, network: Network, machine, winding) -> Callable[[Temperatures | None], ThermalLoad]`: DC copper i_rms² R(T) per coil side at that side's mean node temperature and per end lump at its temperature, by length share (`active_share`); AC per call 6. `None` (first iteration) uses `t_ref_c`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ac_parts_sum_unchanged(): ...         # ac_copper_parts sums to the old ac_copper_loss value
def test_ac_scaling_matches_recompute(): ...   # 8/6 wire case: parts at 120 C scaled to 40 C match a recompute at 40 C within 1 %
def test_iron_total_preserved(): ...           # sum(iron_w_per_m3 * area * depth) == stroke.iron_w * iron_factor, rel 1e-9
def test_copper_total_at_uniform_t(): ...      # uniform temperature T: total copper == q * i_rms^2 * R(T) + AC(T)
def test_density_mode_no_ac(): ...             # wire None -> skin and prox 0, a note
def test_element_w_matches_regions(): ...      # _Side.element_w sums per region to its RegionLoss totals
```
`test_ac_scaling_matches_recompute` and `test_iron_total_preserved` need stroke fields: mark them slow and use `n_angles=12` on the 8/6 `screening` mesh; the other tests use hand-built arrays.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, plus `tests/app/test_losses*.py`, expect PASS.**
- [ ] **Step 5: Commit** `git commit -m "R5b: stroke losses as thermal heat sources"`

### Task 6: Rating core

**Files:**
- Create: `src/srmapp/thermal.py` (core part)
- Test: `tests/app/test_thermal_rating_core.py`

**Interfaces:**
- Consumes: `ThermalSolver`, `ThermalRunaway`, `HotSpot`.
- Produces (pure loop; the losses come from a callable, so the tests use analytic ones):
  - `SpeedRating` (frozen dataclass): `rpm`, `envelope_nm`, `continuous_nm`, `peak_nm`, `continuous_hot_spot: HotSpot`, `peak_hot_spot: HotSpot`, `rotor_c` (mean rotor-iron temperature at continuous), `rotor_peak_c`, `bore_c`, `bore_peak_c`, `n_evaluations`, `transient_steps`, `note`.
  - `BudgetShare` (frozen dataclass): `row`, `rpm`, `hot_spot_rise_k`.
  - `rate_speed(rpm: float, envelope_nm: float, limit_c: float, peak_duration_s: float, solver_for: Callable[[], ThermalSolver], load_at: Callable[[float], Callable | None]) -> SpeedRating`. `load_at(torque)` returns a `load_fn` or None when no stroke reaches the torque. Root finding per call 9, peak transient from the continuous steady state with the step check of call 8. Continuous 0 when even zero torque exceeds the limit or runs away, with the note.

- [ ] **Step 1: Write the failing tests** (a small annulus `ThermalDomain` built by hand, as in `tests/thermal/`, one coil set, one fixed lump; loss = a·T² of torque)

```python
def test_continuous_hits_limit(): ...      # hot spot at continuous_nm within 0.5 K of the limit, or bracket < 1 %
def test_matches_closed_form(): ...        # linear network, loss a*T^2: continuous_nm == sqrt((limit - t_cool) / (a * R_th)) within 1 %
def test_peak_at_least_continuous(): ...
def test_peak_capped_by_envelope(): ...    # large capacity: peak_nm == envelope_nm
def test_coolant_above_limit(): ...        # continuous 0, peak 0, note says no steady state
def test_runaway_is_infeasible(): ...      # load_fn raising ThermalRunaway past a torque: rating below that torque
def test_unreachable_torque(): ...         # load_at None above T*: continuous <= T*
def test_transient_steps_doubled(): ...    # transient_steps >= 50 and the end hot spot moved < 0.1 K at the last doubling
```
- [ ] **Step 2: Run, expect FAIL.** - [ ] **Step 3: Implement.** - [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `git commit -m "R5b: continuous and peak rating per speed"`

### Task 7: `rate` on an evaluated case

**Files:**
- Modify: `src/srmapp/thermal.py` (wiring part)
- Test: `tests/app/test_thermal_rate.py` (slow)

**Interfaces:**
- Consumes: Tasks 3 to 6; `efficiency_map`'s setup steps (`map_request`, `build_map`, `with_end_winding`, `rescale_turns`, `envelope`, `min_copper_stroke`, `stroke_angles`, `stroke_losses`, `phase_current_samples`); `rotor_stress`, `gap_closure`; `UncertaintyBudget`.
- Produces:
  - `Rating` (frozen dataclass): `nominal: tuple[SpeedRating, ...]`, `rated: tuple[SpeedRating, ...]`, `shares: tuple[BudgetShare, ...]`, `limit_c`, `insulation_class`, `cooling: CoolingSetup`, `stress: RotorStress`, `gap: dict[str, GapClosure]` (keys `continuous_max`, `continuous_overspeed`, `peak_max`, `peak_overspeed`, unfavourable growth per call 13), `torque_factor`, `n_strokes`, `notes`, `srmapp_version`.
  - `rate(inputs: CaseInputs, evaluation: Evaluation, *, em_budget: UncertaintyBudget | None = None, n_angles: int = N_ANGLES, solver="ngsolve", workers=None, cache_dir=None, progress=None, cancel=None) -> Rating`. Speeds: base speed plus the R3 map speeds `linspace(max/6, max, 6)`, sorted, unique. Nominal uses no unfavourable rows; rated uses all of `ROWS`, so its strokes are at torque × torque factor. `progress(step, done, total)` with steps `strokes` and `thermal`. Raises `MissingLossData`, `MissingCoolingData` before any solve, `ValueError` for an evaluation without a winding, `InterruptedError` on cancel.
  - `em_torque_total` passed to `coefficients` = `em_budget.total["peak_torque"]` − g/(1 − g) (Global Constraints), None without `em_budget`.
  - Notes always include: placeholder cooling when `cooling.placeholder`, the iron ×2.0 band, the missing continuous measurement (spec §1 item 4), rows not yet measured (call 11), zero iron capacity (call 7), the EM floor (call 14) when it applies.

- [ ] **Step 1: Write the failing slow test** (8/6, 10JNEX900, `screening`, `n_angles=12`, the default cooling, two speeds via a requirements fixture whose base equals max/3)

```python
@pytest.mark.slow
def test_rate_8_6(tmp_path):
    r = rate(inputs, evaluation, n_angles=12, cache_dir=tmp_path)
    for nom, rated in zip(r.nominal, r.rated):
        assert 0 <= rated.continuous_nm <= nom.continuous_nm <= nom.envelope_nm
        assert rated.peak_nm <= nom.peak_nm
        assert nom.continuous_hot_spot.temperature_c <= r.limit_c + 0.5
    assert {s.row for s in r.shares} == set(ROWS)
    assert all(s.hot_spot_rise_k >= 0 for s in r.shares)
    assert any("placeholder" in n for n in r.notes)
    assert r.stress.status in ("ok", "no_fillet")

@pytest.mark.slow
def test_rerate_reuses_strokes(tmp_path): ...   # second rate() with new cooling: no new stroke field files in cache_dir/strokes
```
- [ ] **Step 2: Run, expect FAIL.** - [ ] **Step 3: Implement.** - [ ] **Step 4: Run the slow tests, expect PASS; record the wall time in the commit message.**
- [ ] **Step 5: Commit** `git commit -m "R5b: rate an evaluated case"`

### Task 8: Documentation

**Files:**
- Modify: `CLAUDE.md` (Thermal and rotor stress section: correlations, homogenisation, cooling, network, load, rating; R5b state), `docs/r5-thermal-results.md` (V3 table with the printed and computed values; "Open for R5b" closed item by item, what moves to R5c to R5e)

- [ ] **Step 1: Write both.** - [ ] **Step 2: Run the fast suite, expect PASS.** `PYTHONPATH=src /home/server/srm-forge/.venv/bin/python -m pytest -m "not slow" -q`
- [ ] **Step 3: Commit** `git commit -m "R5b: document cooling and ratings"`
