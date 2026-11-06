# R5a: Thermal Solver and Rotor Stress Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the srmcore foundations of R5: material `thermal` and `mechanical` blocks, a 2D plus lumped thermal solver (steady and transient), and analytic rotor stress and gap closure, proven by gates V1 and V6.

**Architecture:** `srmcore/thermal/` takes the static EM mesh, drops the air gap and solves P1 conduction coupled to a generic lumped network, with one sparse factorisation per cooling setup. `srmcore/post/rotor_stress.py` is closed-form and takes plain data. Nothing here knows about cooling concepts, correlations or ratings; R5b wires those on top.

**Tech Stack:** Python 3.12+, numpy, scipy.sparse, pydantic; skfem in one slow test only.

**Spec:** `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md` (§4.3, §6, §8 V1 and V6, §9, §11).

**Branch:** `r5-thermal` off main. One PR for R5a.

## The R5 stages

The spec covers five separable pieces, so R5 is built as five plans. Each later plan is written when its stage starts, as R4 was.

| Stage | Holds | Gates | Runs |
|---|---|---|---|
| **R5a (this plan)** | material blocks, thermal solver, rotor stress and growth | V1, V6 (8/6, 12/8) | cloud or LattePanda |
| R5b | `docs/r5-sources.md` cooling section, `CoolingSetup`, correlations, winding homogenisation, end-winding and housing network, `srmapp.thermal.rate`, budget rows | V3 | cloud |
| R5c | ratings replace `j_limit`, `Evaluation.rating`, search ranking, version bump | spec §1 item 6 | cloud |
| R5d | web Thermal tab, run report, options-graph axes | | cloud |
| R5e | V0, V2, V4, V5, V6 on the Kiyota rotor, 8/6 and bench-target demonstration | spec §1 items 1, 2, 4, 5 | LattePanda |

## Global Constraints

- SI inside: metres, radians, kelvin differences. Temperatures are °C, in names ending `_c`.
- `thermal` may import `model`, `materials`, `mesh`. It never imports gmsh, skfem, ngsolve or netgen. numpy and scipy only.
- `post/rotor_stress.py` imports only what `post` may: model, materials, physics, fields. `topology` is not allowed there, so pole geometry is computed from `RadialSRMParams` directly.
- Anti-goal: no invented material or chart value. Every number has a cited source with a page in `docs/r5-sources.md`, or the field stays `None`.
- Yield of 10JNEX900: 570 MPa, grade B, von Mises (spec §2 decision 7). E, ν and conductivity at grade C.
- Stress check: safety factor ≥ 1.5 at 1.2 × max speed.
- No version bump in R5a: the bump invalidates every cached map, so it comes once, in R5c.
- Adding a block to a material file must not change `material_digest`.
- Test file basenames are unique across `tests/`. Comments describe the code as it is, not its history.
- Run tests with the shared venv: `/home/server/srm-forge/.venv/bin/python -m pytest`.
- The four papers are at `/home/server/srm-forge/docs/sources/papers/`, git-ignored: the repo is public and they are IEEE copyright. Never commit them. R5a does not need them; R5b (V3) and R5e do.

## Calls made in this plan (not in the spec)

1. Time stepping is backward Euler: L-stable, one factorisation. Accuracy comes from the step count, checked by test.
2. Usable strength = strength × (1 − allowance) with A 0, B 3 %, C 10 %, the B-H grade values, provisional. The spec says "the grade allowance lowers the usable strength" and gives no numbers.
3. The rotor bore is a free surface (no shaft support). A lamination loose on the shaft has the highest hoop stress, so this is the conservative end and press fit stays a non-goal.
4. The slot liner is the thin `slot_air` band the geometry already leaves between coil and iron. No geometry change, no new region, so the EM mesh and every map stay identical.
5. `rotor_slot_air` is removed with the air-gap layers. Rotor surface heat, interpolar faces included, goes to the air-gap node through edges.
6. A rotor with `rotor_fillet_radius` 0 has no stress-concentration factor: `status` is `no_fillet` and `safety_factor` is None. See the first Review Focus line.

## Review Focus

1. **Search candidates have no rotor fillet.** `srmapp.sizing.generator` never sets `rotor_fillet_radius`, so every candidate has a sharp corner and an undefined Kt. `rotor_stress` must return `no_fillet` with nominal stresses, never a number with Kt = 1. Which radius the search uses is an owner decision for R5c (tracker item). Test in Task 6.
2. **Adding a data block silently invalidates caches and labels.** `steel_1010` is every design's shaft, so a digest change would miss every cached map and fail `map_identity`. Test in Task 1.
3. **Thermal runaway.** Copper resistance rises with temperature, so a weak cooling path has no steady state. A person expects "no steady state", not a loop that ends on a false number. `ThermalRunaway` is its own exception so the R5b bisection can treat it as infeasible. Test in Task 4.
4. **A floating body.** A rotor with no link to anything gives a singular matrix. A person expects an error naming the rotor, not NaN temperatures. Test in Task 4.
5. **Imported iron (DXF).** The domain must build from a case with `stator_hole_air` and `rotor_hole_air`, and rotor stress must read "not available". Tests in Tasks 3 and 6.

---

### Task 1: Material `thermal` and `mechanical` blocks

**Files:**
- Modify: `src/srmcore/materials/schema.py`, `src/srmcore/maps/identity.py:12-19`
- Test: `tests/materials/test_material_blocks.py`, `tests/maps/test_identity.py`

**Interfaces:**
- Produces, in `materials/schema.py`, both on `_Sourced` as optional fields (default None):
  - `ThermalData`: `conductivity` (W/(m·K), in-plane, > 0), `conductivity_through_stack: float | None`, `specific_heat: float | None` (J/(kg·K)), `expansion: float | None` (1/K), `provenance: Provenance`, `confidence: Literal["A","B","C"]`, `temperature_c: float = 20.0`
  - `MechanicalData`: `youngs_modulus` (Pa, > 0), `poisson_ratio` (0 < ν < 0.5), `yield_strength: float | None` (Pa), `tensile_strength: float | None` (Pa), `brittle: bool = False`, `provenance`, `confidence` (E and ν), `strength_confidence: Literal["A","B","C"]`, `temperature_c: float = 20.0`
  - `_Sourced.thermal: ThermalData | None = None`, `_Sourced.mechanical: MechanicalData | None = None`
  - `MechanicalData.strength` property: tensile when brittle, else yield.

- [ ] **Step 1: Write the failing tests**

```python
# tests/materials/test_material_blocks.py
def test_ductile_needs_yield(): ...      # brittle=False, yield None -> ValidationError
def test_brittle_needs_tensile(): ...    # brittle=True, tensile None -> ValidationError
def test_strength_picks_by_flag(): ...   # brittle -> tensile, else yield
def test_poisson_bounds(): ...           # 0.5 and 0.0 rejected
def test_blocks_default_none(): assert load_material("M19").mechanical is None
```

```python
# tests/maps/test_identity.py, beside test_loss_block_does_not_change_digest
@pytest.mark.parametrize("block", ["thermal", "mechanical"])
def test_data_block_does_not_change_digest(block):
    raw = (library._data_dir() / "steel_1010.json").read_bytes()
    record = json.loads(raw); record.pop(block, None)
    bare = json.dumps(record).encode()
    record[block] = {"anything": 1}
    assert material_digest(json.dumps(record).encode()) == material_digest(bare)
```

- [ ] **Step 2: Run them, expect failure**

Run: `/home/server/srm-forge/.venv/bin/python -m pytest tests/materials/test_material_blocks.py tests/maps/test_identity.py -q`
Expected: FAIL (`ThermalData` missing, digest differs).

- [ ] **Step 3: Implement**

Add the two models and fields. In `material_digest`, pop `loss`, `thermal` and `mechanical`, and extend its docstring: none of them can change a magnetostatic map.

- [ ] **Step 4: Run them, expect pass.** Same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/materials/schema.py src/srmcore/maps/identity.py tests/materials/test_material_blocks.py tests/maps/test_identity.py
git commit -m "R5a: material thermal and mechanical blocks, left out of the design hash"
```

### Task 2: Sources and library values

**Files:**
- Create: `docs/r5-sources.md`
- Modify: `src/srmcore/materials/data/10JNEX900.json`, `copper.json`, `steel_1010.json`
- Test: `tests/materials/test_material_blocks.py`

**Interfaces:**
- Consumes: Task 1 schema.
- Produces: `load_material("10JNEX900").mechanical.strength == 570e6`, `strength_confidence == "B"`, `.thermal.conductivity == 18.6`; a recorded Kt formula for Task 6.

This task reads sources; it writes no logic. Use the `docs/r3-sources.md` layout: summary table (item, source, grade, status), then one section per item. Say where a value could not be found.

- [ ] **Step 1: Read and record, in `docs/r5-sources.md`**

| Item | Where to look | Rule |
|---|---|---|
| 10JNEX900 yield, E, ν, k | Ou et al. 2021 accepted manuscript, https://publikationen.bibliothek.kit.edu/1000125982/128560422, Fig. 13 and Table I | Confirm the spec §4.3 numbers against the text. Read their ref. [24] for test temperature and cutting method if reachable |
| 10JNEX900 specific heat, expansion, through-stack k | JFE documents in `docs/sources/materials/`, then literature on 6.5 % Si steel | The spec records no value. Not found means the field stays `None` and the section says so. Do not borrow a value from another steel without the source saying it applies |
| copper k, c, α | a handbook or standard readable online | cited page |
| steel_1010 k, c, α, E, ν, yield | a handbook or datasheet readable online | cited page, grade from the source type |
| Kt of a shoulder fillet in tension | Peterson's Stress Concentration Factors, or Roark's Formulas for Stress and Strain | Record the exact formula or curve-fit coefficients, its validity range and the page. Task 6 codes exactly this |

- [ ] **Step 2: Write the failing test**

```python
def test_10jnex900_strength_from_ou_2021():
    m = load_material("10JNEX900").mechanical
    assert m.strength == 570e6 and not m.brittle
    assert m.strength_confidence == "B" and m.confidence == "C"
    assert m.youngs_modulus >= 200e9 and m.poisson_ratio == 0.33

def test_10jnex900_conductivity_grade_c():
    t = load_material("10JNEX900").thermal
    assert t.conductivity == 18.6 and t.confidence == "C"
```

- [ ] **Step 3: Run it, expect failure.** `-k 10jnex900`. Expected: FAIL (`mechanical` is None).

- [ ] **Step 4: Add the blocks to the three JSON files.** For the 200–210 GPa range of E, use 200 GPa: the lower value gives more growth, the conservative end for gap closure.

- [ ] **Step 5: Run the material and identity tests, expect pass**

Run: `/home/server/srm-forge/.venv/bin/python -m pytest tests/materials tests/maps/test_identity.py -q`
Expected: PASS, with `design_hash` of every existing test design unchanged.

- [ ] **Step 6: Commit**

```bash
git add docs/r5-sources.md src/srmcore/materials/data tests/materials/test_material_blocks.py
git commit -m "R5a: cited thermal and mechanical data for 10JNEX900, copper, steel_1010"
```

### Task 3: Thermal domain from the static mesh

**Files:**
- Create: `src/srmcore/thermal/__init__.py`, `src/srmcore/thermal/domain.py`
- Modify: `tests/test_import_rules.py` (row `"thermal": {"model", "materials", "mesh"}`)
- Test: `tests/thermal/test_thermal_domain.py`

**Interfaces:**
- Consumes: `StaticMesh` (`mesh/static.py`), `RadialSRMParams`.
- Produces, in `thermal/domain.py`:

```python
EXCLUDED_REGIONS = ("airgap_stator", "airgap_rotor", "rotor_slot_air", "stator_outer_air")

@dataclass(frozen=True)
class ThermalDomain:
    nodes: np.ndarray            # (n, 2), stator nodes then rotor nodes, unused nodes dropped
    triangles: np.ndarray        # (m, 3), stator elements then rotor elements
    element_kind: np.ndarray     # (m,) str: stator_iron, rotor_iron, shaft, coil, liner, air
    stator_elements: np.ndarray  # rows of static.stator.triangles kept, in thermal order
    rotor_elements: np.ndarray   # rows of static.rotor.triangles kept
    coil_elements: dict[str, np.ndarray]   # coil region name -> thermal element rows
    outer_edges: np.ndarray      # (k, 2) stator outer surface
    bore_edges: np.ndarray       # every other stator boundary edge
    rotor_edges: np.ndarray      # rotor boundary edges

    def from_em(self, stator_values: np.ndarray, rotor_values: np.ndarray) -> np.ndarray: ...
    # per-element arrays in EM order -> thermal order

def thermal_domain(static: StaticMesh, machine: RadialSRMParams) -> ThermalDomain: ...
```

A `slot_air` element is `liner` when its centroid lies within `slot_liner_thickness + 2 * stator_fillet_radius` of both a coil boundary and a stator-iron boundary, by exact point-to-segment distance. The stator and rotor stay separate node sets: they meet only through lumps. An edge is outer when both its nodes are at radius ≥ `stator_outer_radius × (1 − 1e-6)`. Boundary edges are those used by exactly one kept triangle.

- [ ] **Step 1: Write the failing tests**

```python
def test_gap_regions_removed(static_8_6, domain_8_6): ...
    # no element from EXCLUDED_REGIONS; element count == EM total - excluded
def test_em_rows_map_one_to_one(static_8_6, domain_8_6):
    q = np.arange(len(static_8_6.stator.triangles), dtype=float)
    r = np.zeros(len(static_8_6.rotor.triangles))
    out = domain_8_6.from_em(q, r)
    # the vertices of thermal element e equal those of EM element stator_elements[e]
def test_outer_edges_lie_on_the_od(...): ...      # total length == 2π·R within 0.5 %
def test_rotor_edges_close(...): ...              # every node on rotor_edges has degree 2
def test_liner_band_area(...):
    # area of liner elements within 25 % of n_coils × (t × depth + (t + 2f) × build), from coil_geometry
def test_slot_centre_is_not_liner(...): ...
def test_imported_iron_builds(...): ...           # a design with ImportedIron from parametric_iron; hole air kept as air
def test_outer_air_design_keeps_outer_edges(...): ...   # MeshSettings.outer_air_thickness > 0
```

Use module-scoped fixtures on `make_8_6` at `screening`.

- [ ] **Step 2: Run them, expect failure.** Run: `.../python -m pytest tests/thermal/test_thermal_domain.py tests/test_import_rules.py -q`. Expected: FAIL (no module).

- [ ] **Step 3: Implement `thermal_domain`.**

- [ ] **Step 4: Run them, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/thermal tests/thermal/test_thermal_domain.py tests/test_import_rules.py
git commit -m "R5a: thermal domain from the static mesh"
```

### Task 4: Thermal problem and steady solve (gate V1, steady)

**Files:**
- Create: `src/srmcore/thermal/model.py`, `src/srmcore/thermal/solve.py`
- Test: `tests/thermal/test_thermal_steady.py`

**Interfaces:**
- Consumes: `ThermalDomain` (tests build it directly on their own grids, so `from_em` fields may be empty arrays).
- Produces, `thermal/model.py`:

```python
@dataclass(frozen=True)
class Lump:
    name: str
    capacity: float = 0.0            # J/K
    fixed_c: float | None = None     # a set temperature: coolant inlet, ambient
    hot_spot: bool = False           # counts in the hot spot (end windings)

@dataclass(frozen=True)
class LumpLink:  a: str; b: str; conductance: float            # W/K
@dataclass(frozen=True)
class EdgeLink:  edges: np.ndarray; lump: str; h: float        # W/(m²·K), area = edge length × depth
@dataclass(frozen=True)
class AreaLink:  elements: np.ndarray; lump: str; g: float     # W/(m²·K), area = element area

@dataclass(frozen=True)
class ThermalProblem:
    domain: ThermalDomain
    conductivity: np.ndarray    # (m,) W/(m·K), in-plane
    capacity: np.ndarray        # (m,) J/(m³·K)
    depth: float                # m
    lumps: tuple[Lump, ...]
    links: tuple[LumpLink | EdgeLink | AreaLink, ...]

@dataclass(frozen=True)
class ThermalLoad:
    element_w_per_m3: np.ndarray
    lump_w: Mapping[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class Temperatures:
    field: np.ndarray            # (n,) °C
    lumps: dict[str, float]      # °C

class ThermalModelError(ValueError): ...
class ThermalRunaway(ThermalModelError): ...
```

- Produces, `thermal/solve.py`:

```python
RUNAWAY_C = 1000.0
LoadFn = Callable[[Temperatures | None], ThermalLoad]   # None on the first call

class ThermalSolver:
    def __init__(self, problem: ThermalProblem): ...     # validates, assembles
    def steady(self, load: LoadFn, tol_k: float = 0.01, max_iter: int = 50) -> Temperatures: ...
    def heat_to_fixed(self, t: Temperatures) -> dict[str, float]: ...   # W into each fixed lump
```

Assemble one sparse matrix over field nodes plus free lumps, with depth multiplying conduction. `EdgeLink` and `AreaLink` use consistent P1 integrals, so a link to a lump adds h∫N_iN_j on the nodes and −h∫N_i on the lump coupling. Fixed lumps go to the right-hand side. Factorise once with `scipy.sparse.linalg.splu` and reuse it for every iteration. `steady` calls `load(previous)`, solves, and stops when the largest field or lump temperature moves by less than `tol_k`. It raises `ThermalRunaway` when the temperature passes `RUNAWAY_C` or `max_iter` runs out while the change is not shrinking.

`__init__` raises `ThermalModelError` on: an unknown lump in a link, a non-positive `conductance`, `h` or `g`, wrong array lengths, a non-positive conductivity. `steady` raises it when a connected component (`scipy.sparse.csgraph.connected_components`) has no fixed lump, naming "stator", "rotor" or the lump.

- [ ] **Step 1: Write the failing tests**

```python
def test_slab_uniform_heat_robin_ends():
    # strip 2a wide, k, q, h at both ends to a fixed lump at T∞
    # T(x) = T∞ + q·a/h + q(a² − x²)/(2k); assert max error < 1e-9 × (Tmax − T∞)

def test_annulus_uniform_heat():
    # inner radius a adiabatic, outer b at T_b (EdgeLink, h = 1e9), polar grid
    # T(r) = T_b + q(b² − r²)/(4k) + q·a²·ln(r/b)/(2k); assert max rel. error < 1e-3

def test_manufactured_solution_second_order():
    # unit square, T = sin(πx)sin(πy), q = 2π²kT, boundary held near 0
    # L2 error on h and h/2: ratio > 3

def test_energy_balance():
    # sum(heat_to_fixed) == total load to 1e-9 relative, field and lump load together

def test_depth_scales_conduction_and_edges_alike():
    # depth × 2 with load per m³ unchanged leaves temperatures unchanged

def test_temperature_dependent_load_converges():
    # one lump, P(T) = P0(1 + αT), G > αP0: T = (P0 + G·Tf)/(G − αP0) within tol_k

def test_runaway_is_reported():
    # G < αP0 -> pytest.raises(ThermalRunaway)

def test_floating_rotor_refused():
    # two-body domain, rotor unlinked -> ThermalModelError with "rotor" in the message

def test_unknown_lump_refused(): ...
```

- [ ] **Step 2: Run them, expect failure.** `.../python -m pytest tests/thermal/test_thermal_steady.py -q`. Expected: FAIL (no module).

- [ ] **Step 3: Implement `model.py` and `ThermalSolver.__init__`, `steady`, `heat_to_fixed`.**

- [ ] **Step 4: Run them, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/thermal tests/thermal/test_thermal_steady.py
git commit -m "R5a: thermal problem, lumped links and steady solve (V1 steady)"
```

### Task 5: Transient solve and hot spot (gate V1, transient)

**Files:**
- Modify: `src/srmcore/thermal/solve.py`, `src/srmcore/thermal/__init__.py` (public names)
- Test: `tests/thermal/test_thermal_transient.py`

**Interfaces:**
- Consumes: Task 4.
- Produces:

```python
@dataclass(frozen=True)
class HotSpot:
    temperature_c: float
    location: str          # coil region name or lump name

@dataclass(frozen=True)
class Transient:
    times_s: np.ndarray        # (n + 1,)
    hot_spot_c: np.ndarray     # (n + 1,)
    final: Temperatures

ThermalSolver.hot_spot(self, t: Temperatures) -> HotSpot
ThermalSolver.transient(self, start: Temperatures, load: LoadFn, duration_s: float, n_steps: int = 200) -> Transient
```

Backward Euler with lumped (diagonal) capacity from element capacity and lump `capacity`, and one factorisation of (C/dt + K) per call. The load is evaluated at the previous step. A floating component is allowed here when it has capacity: adiabatic parts are legal in a transient. `hot_spot` covers the nodes of `domain.coil_elements` and lumps with `hot_spot=True`, and raises `ThermalModelError` when neither exists.

- [ ] **Step 1: Write the failing tests**

```python
def test_lumped_rc_step():
    # one lump C, G to a fixed lump, load P: T(t) = Tf + (P/G)(1 − exp(−tG/C))
    # n_steps = 200 over one time constant: |error| < 0.5 % of the rise

def test_time_step_is_first_order():
    # error at n_steps and 2·n_steps: ratio between 1.8 and 2.2

def test_adiabatic_element_heating():
    # field with no links: T rises by q·t/(ρc) everywhere, to 1e-9 relative

def test_transient_settles_on_steady():
    # long run from the fixed temperature ends within 0.1 K of steady()

def test_hot_spot_finds_end_winding():
    # lump hot_spot=True hotter than every coil node -> location is the lump name

def test_hot_spot_finds_coil_region(): ...
```

- [ ] **Step 2: Run them, expect failure.** `.../python -m pytest tests/thermal/test_thermal_transient.py -q`. Expected: FAIL (`transient` missing).

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run all of `tests/thermal -q`, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/thermal tests/thermal/test_thermal_transient.py
git commit -m "R5a: transient solve and hot spot (V1 transient)"
```

### Task 6: Analytic rotor stress

**Files:**
- Create: `src/srmcore/post/rotor_stress.py`
- Test: `tests/post/test_rotor_stress.py`

**Interfaces:**
- Consumes: `MechanicalData` (Task 1), the Kt formula recorded in `docs/r5-sources.md` (Task 2).
- Produces:

```python
SAFETY_FACTOR = 1.5
OVERSPEED = 1.2
STRENGTH_GRADE_ALLOWANCE = {"A": 0.0, "B": 0.03, "C": 0.10}   # provisional, as for the B-H grades

def pole_half_width(machine: RadialSRMParams, r: float) -> float: ...   # m, follows topology.radial._pole_side
def pole_force_per_depth(machine, density: float, omega: float) -> float: ...   # N/m, one rotor pole
def root_stress_concentration(machine: RadialSRMParams) -> float | None: ...    # None when the fillet is 0

@dataclass(frozen=True)
class RotorStress:
    status: Literal["ok", "no_strength_data", "no_fillet", "imported_iron"]
    note: str
    check_speed_rpm: float
    bore_stress: float | None         # Pa
    root_stress: float | None         # Pa, nominal × Kt; nominal when status is no_fillet
    stress_concentration: float | None
    governing: Literal["bore", "pole_root"] | None
    criterion: Literal["von_mises", "max_principal"] | None
    usable_strength: float | None     # Pa, after the grade allowance
    safety_factor: float | None
    speed_limit_rpm: float | None     # highest max speed that keeps SAFETY_FACTOR

def rotor_stress(machine: RadialSRMParams, density: float, mechanical: MechanicalData | None,
                 max_speed_rpm: float, rotor_temperature_c: float | None = None) -> RotorStress: ...
```

Model (spec §9), with a = shaft radius, b = `rotor_yoke_outer_radius`, ω at `OVERSPEED × max_speed_rpm`, N = rotor poles:

```
rim load        p   = N · F / (2π·b)                      F = pole_force_per_depth
bore hoop       σ_a = ρω²/4 · ((3+ν)b² + (1−ν)a²) + 2b²/(b²−a²) · p
root nominal    σ_n = F / (2 · pole_half_width(b))
root peak       σ_r = Kt · σ_n
```

Both points are uniaxial on a free surface, so von Mises and maximum principal stress are equal there; only the strength differs (`mechanical.strength`). Every stress scales with ω², so `speed_limit_rpm = max_speed_rpm × sqrt(safety_factor / SAFETY_FACTOR)`. The note says when `rotor_temperature_c` is above the block's `temperature_c`: strength is at room temperature, the rotor runs hotter. The stacking factor plays no part: each lamination carries its own mass, so `density` is the solid density.

- [ ] **Step 1: Write the failing tests**

```python
def test_bore_hoop_formula():    # bore_stress equals the σ_a expression above, F from pole_force_per_depth, ρ 7490, ν 0.33
def test_pole_force_matches_the_mesh():
    # ρω²∫r dA over one pole of the 8/6 rotor_iron mesh (r > yoke radius): within 1 %
def test_pole_force_with_taper(): ...     # same with rotor_pole_taper ≠ 0
def test_kt_from_the_cited_formula(): ...  # values at the two ends of the recorded validity range
def test_kt_falls_with_radius(): ...
def test_speed_limit_gives_exactly_the_safety_factor():
    s = rotor_stress(p, 7490, mech, 20000)
    again = rotor_stress(p, 7490, mech, s.speed_limit_rpm)
    assert again.safety_factor == pytest.approx(SAFETY_FACTOR)
def test_grade_b_lowers_strength(): assert s.usable_strength == pytest.approx(570e6 * 0.97)
def test_brittle_uses_tensile(): ...
def test_no_data_reads_no_strength(): # mechanical None -> status no_strength_data, stresses still given
def test_zero_fillet_gives_no_factor():
    # rotor_fillet_radius 0 -> status no_fillet, safety_factor None, root_stress nominal
def test_imported_iron_not_available():
    # status imported_iron, note contains "FE stress is R10", every stress None
def test_hot_rotor_note(): ...
def test_speed_must_be_positive(): ...    # ValueError at 0
```

- [ ] **Step 2: Run them, expect failure.** `.../python -m pytest tests/post/test_rotor_stress.py -q`. Expected: FAIL (no module).

- [ ] **Step 3: Implement.** The imported-iron note reads "analytic stress not available for imported rotor iron, FE stress is R10".

- [ ] **Step 4: Run them, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/post/rotor_stress.py tests/post/test_rotor_stress.py
git commit -m "R5a: analytic rotor stress and speed limit"
```

### Task 7: Rotor growth and gap closure

**Files:**
- Modify: `src/srmcore/post/rotor_stress.py`
- Test: `tests/post/test_rotor_growth.py`

**Interfaces:**
- Consumes: Task 6 helpers, `ThermalData.expansion`.
- Produces:

```python
@dataclass(frozen=True)
class GapClosure:
    centrifugal: float               # m, disc plus pole elongation at the pole tip
    rotor_thermal: float | None      # m, None without expansion data
    stator_thermal: float | None     # m
    closure: float | None            # m, rotor growth minus bore growth; None without expansion data
    note: str

def gap_closure(machine, density: float, mechanical: MechanicalData, rotor_expansion: float | None,
                stator_expansion: float | None, rpm: float, rotor_temperature_c: float,
                stator_temperature_c: float, reference_c: float = 20.0) -> GapClosure: ...
```

Disc displacement at b: u = (b/E)(σθ(b) − ν·p), plane stress, free bore, rim load p. Pole elongation: ∫ σ(r)/E dr from b to R, with σ(r) = ρω²/w(r) · ∫ r′w(r′)dr′ from r to R. Thermal: α·ΔT·r at R for the rotor, at `bore_radius` for the stator. The stator has no centrifugal term.

- [ ] **Step 1: Write the failing tests**

```python
def test_thin_ring_growth():      # a → b, no poles load: u → ρω²b³/E within 1 %
def test_uniform_pole_elongation():
    # constant width: ρω²/E · (R²(R−r0)/2 − (R³−r0³)/6), to 1e-6 relative
def test_thermal_growth_cancels_for_equal_temperature_and_alpha():
    # closure thermal part == α·ΔT·(R − bore) (negative: the gap opens)
def test_growth_scales_with_speed_squared(): ...
def test_missing_expansion_keeps_centrifugal():
    # closure None, centrifugal given, note says which expansion is missing
```

- [ ] **Step 2: Run them, expect failure.** Expected: FAIL (`gap_closure` missing).

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run them, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/post/rotor_stress.py tests/post/test_rotor_growth.py
git commit -m "R5a: rotor growth and gap closure"
```

### Task 8: Gate V6, FE reference for the rotor stress

**Files:**
- Create: `tests/post/rotor_elastic_fe.py` (helper), `tests/post/test_rotor_stress_fe.py`, `docs/r5-thermal-results.md`

**Interfaces:**
- Consumes: `build_static_mesh`, Task 6 and 7.
- Produces: `rotor_elastic_fe(static, density, youngs_modulus, poisson_ratio, omega) -> FeStress(bore_peak, root_peak, tip_displacement)`, test-only. It uses skfem, which the import rules allow in tests only. The results file holds the V6 table.

Plane-stress `ElementVector(ElementTriP2)` on the `rotor_iron` elements of the static mesh, with body force ρω²r, free bore, three rigid-body DOFs pinned on a self-equilibrated load. Peak von Mises at quadrature points: `bore_peak` within 1 mm of the bore, `root_peak` within 2 fillet radii of a pole root.

Pass rule for V6, set here because the spec leaves it to the plan: the FE has converged (the last two of `screening`, `full`, `reference` differ by under 2 %), and bore and root analytic values are within 15 % of the FE, with the analytic peak not more than 5 % below the FE peak. If it fails, the spec's action is to revise the analytic model or its Kt. Do not widen the limit.

- [ ] **Step 1: Write the slow test**

```python
@pytest.mark.slow
@pytest.mark.parametrize("make", [make_8_6, make_12_8])
def test_analytic_stress_against_fe(make):
    # FE at screening, full, reference; assert the convergence and pass rules above
    # also tip growth: analytic centrifugal within 15 % of FE tip_displacement
```

- [ ] **Step 2: Run it**

Run: `.../python -m pytest tests/post/test_rotor_stress_fe.py -m slow -q`
Expected: it runs to a real comparison. A numeric failure here is a finding, not a test bug. Follow the spec's action and record what changed.

- [ ] **Step 3: Record in `docs/r5-thermal-results.md`.** The file opens with what it holds (gates V1 to V6) and states that V0, V2, V3, V4, V5 are pending. Table for V6: machine, preset, FE bore and root, analytic bore and root, error. Include the commit hash.

- [ ] **Step 4: Commit**

```bash
git add tests/post/rotor_elastic_fe.py tests/post/test_rotor_stress_fe.py docs/r5-thermal-results.md
git commit -m "R5a: gate V6, analytic rotor stress against a 2D elastic FE"
```

### Task 9: Docs and the whole-suite check

**Files:**
- Modify: `CLAUDE.md` (Current state; a short "Thermal (R5)" section; `thermal` row in the import table)

- [ ] **Step 1: Add to `CLAUDE.md`:** R5a's state in Current state, the `thermal` row in the import table, and a section naming `thermal/domain.py`, `model.py`, `solve.py`, `post/rotor_stress.py`, what each gives, and that R5b holds the cooling wiring.

- [ ] **Step 2: Run the fast suite**

Run: `/home/server/srm-forge/.venv/bin/python -m pytest -m "not slow" -q -x`
Expected: PASS. It takes about 1 h, so run it in the background. `tests/maps/test_identity.py` is the check that no map hash changed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "R5a: document the thermal core"
```

- [ ] **Step 4:** Open the PR with `superpowers:finishing-a-development-branch`; merge after CI is green. Update the project doc and the Progress tab in the same session.
