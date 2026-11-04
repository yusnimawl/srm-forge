# R4a 3D Reference Model and Gates G0–G2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline nonlinear 3D magnetostatic model (NGSolve) of TEAM 24 and of srmcore radial machines, then run gates G0 (cost), G2 (3D slab equals 2D) and G1 (3D TEAM 24 vs the measured torque and flux) and record the verdict.

**Architecture:** A package `tools/end3d/` (never imported by `src/`) builds `netgen.occ` solids: the 2D outline extruded over half the stack, coils as U-shaped solids (two sides plus an end bridge), an air region beyond the stack end, and a z = 0 mirror plane. Coil current density comes from a conduction solve in each coil, so it is divergence-free by construction. The field is A in H(curl), with the energy written as a BSpline in |B|² sampled from the srmcore `ReluctivityLaw`, solved by Newton. Post-processing gives ψ, an Arkkio shell torque, co-energy and the TEAM 24 rotor-pole flux.

**Tech Stack:** Python 3.12, NGSolve 6.2.2608 with `netgen.occ` (in `.venv`), numpy; srmcore and `tests/team24_fixture.py` as inputs; pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-r4-end-effects-design.md`

**Scope:** spec §4 gates G0, G1, G2 and the 3D tool from §7. Not in this plan: the sweep (§6), G3, G4, G5, the correction layer, budget, UI and ranking (§5, §7, §8). Those go in plan R4b, written after G1 passes, because the correction's form depends on what the 3D runs show. If G1 fails, the R4b plan covers spec decision 3 instead (record the finding, put the measured gap into the budget).

## Global Constraints

- Branch `r4-end-effects` off main. One PR at the end of R4a; CI green before merge. No srmcore, srmapp, srmweb or `web/` version bump in R4a (`src/` code does not change).
- `tools/end3d/` is never imported by `src/`. It may import srmcore, `ngsolve`, `netgen` and `tests/` fixtures (as `tools/femm_fixtures.py` does). `tests/test_import_rules.py` must still pass.
- Add `"tools"` to `[tool.pytest.ini_options] pythonpath` in `pyproject.toml`; tests import `from end3d import ...`.
- Tests live in `tests/end3d/`, file names `test_end3d_*.py` (basenames must be unique). They `pytest.importorskip("ngsolve")`. Any test over about 30 s is `@pytest.mark.slow`.
- SI units inside (metres, radians, amperes); radial machines come from `conftest.make_8_6` etc. and `srmcore.topology.radial.parametric_outline`.
- **No constant, perturbation size or mesh choice is tuned after looking at the measured TEAM 24 or Krishnan data** (spec decision 1). Perturbation sizes for G1 are fixed in Task 9 before G1 runs.
- Runs happen on the LattePanda (16 threads, 30 GB RAM). Long runs are scripts, run in the background, with JSON output; never inside the fast suite.
- Results go to `docs/r4-end-effect-results.md` (new) and `docs/validation/r4_*.json`. Every merge updates the wiki Progress tab and the project doc (CLAUDE.md owner rules).
- Comments describe the code as it is, not task history.
- Mirror model: every model is the half z ≥ 0 with B·n = 0 on z = 0 (tangential A = 0). Full-machine ψ, energy, torque and flux are 2 × the half-model integrals. A slab has B·n = 0 on both z faces and no end region.

## Review Focus

1. **Newton fails at saturation** (TEAM 24 at 7.41 A saturates the pole corners). `solve3d` must return `converged=False` with the residual history, never a number that looks converged, and the G-scripts must refuse to record a non-converged point. Test in Task 3.
2. **Mirror factor of 2 applied twice or not at all.** Full-machine ψ and torque must scale with slab depth (Task 5) and equal the 2D values per the same stack length (Task 8).
3. **Sign of torque or flux flipped** against the 2D model (coil current direction, rotor angle sign). G2 compares signed values with 2D, not absolute values. Test in Task 8.
4. **The finest mesh runs out of RAM** partway through a G1 run and loses the earlier levels. Scripts write JSON after each level and take `--max-dofs`; a level whose DOF count exceeds it is skipped and recorded as skipped. Test in Task 6.
5. **|B| beyond the B-H data** (corner singularities can exceed 3 T). The BSpline must continue with slope ν0/2 in |B|², not extrapolate a polynomial. Test in Task 1.

---

### Task 1: Package, material energy

**Files:**
- Create: `tools/end3d/__init__.py`, `tools/end3d/material.py`
- Modify: `pyproject.toml` (pytest `pythonpath` gets `"tools"`)
- Test: `tests/end3d/test_end3d_material.py`

**Interfaces:**
- Produces: `energy_bspline(law: ReluctivityLaw, b_max: float = 6.0, n: int = 600) -> ngsolve.BSpline` — the magnetic energy density w as a function of s = |B|² (J/m³), order 3, knots dense near 0 (geometric spacing in |B|, first knot at 1e-4 T), sampled from `law.energy_density`, so dw/ds = ν(s)/2. Beyond `b_max` the spline continues linearly with slope ν0/2. `LinearLaw` (air, copper) gives the exact `nu/2 * s`.
- Produces: `nu_from_bspline(w, s: np.ndarray) -> np.ndarray` (2 × numerical derivative), for tests and debugging.

- [ ] **Step 1: Write failing tests**
  - `test_energy_derivative_matches_law`: for `library_law("10JNEX900")` and the TEAM 24 `steel_law()`, `nu_from_bspline` at B = 0.1, 0.5, 1.0, 1.5, 1.9, 2.2 T is within 1e-3 relative of `law.nu_dnu(B**2)[0]`.
  - `test_linear_law_exact`: `VACUUM` gives ν0 to 1e-9 relative at B = 0.01 and 3 T.
  - `test_tail_is_vacuum_slope`: at B = 8 T (beyond `b_max`) the derivative equals ν0 within 1 %.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_material.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `energy_bspline` and `nu_from_bspline` in `tools/end3d/material.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git add pyproject.toml tools/end3d tests/end3d && git commit -m "end3d: material energy BSpline from srmcore laws"`

### Task 2: Coil current density by conduction solve

**Files:**
- Create: `tools/end3d/coil.py`
- Test: `tests/end3d/test_end3d_coil.py`

**Interfaces:**
- Consumes: an NGSolve `Mesh` whose coil solids are named `coil_<k>` and whose coil faces on the mirror plane are named `coil_<k>_in` and `coil_<k>_out`.
- Produces: `coil_current_density(mesh, coil: str, ampere_turns: float, order: int = 2) -> ngsolve.CoefficientFunction`. Solves −∇·∇φ = 0 in the coil (H1, `definedon` the coil) with φ = 1 on `_in`, φ = 0 on `_out`, natural BC elsewhere. Returns J = −∇φ scaled so that the flux of J through `_in` equals `ampere_turns` (A). It is zero outside the coil.
- Produces: `face_current(mesh, j, face: str) -> float` (∫ J·n dA over a named face).

The coil is U-shaped in the half model: two sides from z = 0 to the end bridge, so φ runs from one mirror face to the other and J is divergence-free with continuous normal flux at z = 0 by mirror symmetry.

- [ ] **Step 1: Write failing tests** on a U-shaped rectangular coil in an air box (built in the test with `netgen.occ`: two 10 × 20 mm sides, 50 mm long, joined by a 10 mm bridge):
  - `test_current_through_in_and_out`: `face_current` on `_in` is `ampere_turns` and on `_out` is −`ampere_turns`, each to 1e-6 relative.
  - `test_current_through_internal_section`: through an internal cross-section face of each side (name it in the geometry), `abs(face_current)` equals `ampere_turns` to 1e-3 relative.
  - `test_zero_outside_coil`: ∫|J|² over the air region is 0.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_coil.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `coil_current_density` and `face_current` in `tools/end3d/coil.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "end3d: coil current density from a conduction solve"`

### Task 3: Nonlinear 3D solver

**Files:**
- Create: `tools/end3d/solve.py`
- Test: `tests/end3d/test_end3d_solve.py`

**Interfaces:**
- Consumes: `energy_bspline` (Task 1), `coil_current_density` (Task 2).
- Produces: `@dataclass(frozen=True) class Model3D: mesh: ngsolve.Mesh; laws: dict[str, ReluctivityLaw]` (material name → law; every volume material of the mesh must have an entry, else `ValueError` naming it); `coils: tuple[str, ...]`; `dirichlet: str` (face names joined by `|`, default `"sym_z|outer"`); `order: int = 2`.
- Produces: `@dataclass(frozen=True) class Solution3D: a: ngsolve.GridFunction; converged: bool; iterations: int; residuals: tuple[float, ...]; ndof: int; seconds: float; peak_rss_bytes: int`.
- Produces: `solve3d(model: Model3D, ampere_turns: Mapping[str, float], initial: ngsolve.GridFunction | None = None, max_iter: int = 30) -> Solution3D`.

Formulation: H(curl), `nograds=True`, order `model.order`, Dirichlet on `model.dirichlet`. Energy functional Σ_regions ∫ w_region(curl A · curl A) dx − ∫ J·A dx, plus a regularisation 1e-6 · ν0 · A·A in air and coil regions only. Newton with `AssembleLinearization`; linear step by CG with a `"bddc"` preconditioner (relative tolerance 1e-10); damped line search on the energy (halve the step up to 8 times). Stop when the update's energy norm is below 1e-8 of the solution's and the residual is below 1e-8 of the first residual (the 2D adapters' tolerances). It never raises on non-convergence: it returns `converged=False`. `peak_rss_bytes` comes from `resource.getrusage(RUSAGE_SELF).ru_maxrss`.

- [ ] **Step 1: Write failing tests**
  - `test_current_sheet_field` (linear): a slab (both z faces Dirichlet, so 2D-equivalent) holding two parallel thin conductors with opposite currents. The gap field B between them, far from their edges, equals μ0·K within 1 %.
  - `test_nonlinear_converges_and_reports`: an iron block (TEAM 24 `steel_law`) inside a U coil at an ampere-turn count that saturates it (B > 1.9 T in the block). `converged` is True, `residuals` decreases to below 1e-8 of the first, `ndof > 0`, `peak_rss_bytes > 0`.
  - `test_nonconvergence_is_reported`: the same with `max_iter=1`. `converged` is False, no exception.
  - `test_missing_law_raises`: a mesh material without a law raises `ValueError` whose message contains the material name.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_solve.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `Model3D`, `Solution3D`, `solve3d` in `tools/end3d/solve.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "end3d: nonlinear H(curl) Newton solver with a mirror plane"`

### Task 4: TEAM 24 3D geometry

**Files:**
- Create: `tools/end3d/team24.py`
- Test: `tests/end3d/test_end3d_team24_geometry.py`

**Interfaces:**
- Consumes: constants from `tests/team24_fixture.py` (`R_STATOR_OUT`, `R_YOKE_IN`, `R_STATOR_BORE`, `POLE_WIDTH_STATOR`, `R_ROTOR_TIP`, `R_SHAFT`, `R_HUB`, `POLE_WIDTH_ROTOR`, `DEPTH`, `ROTOR_ANGLE`, `TURNS`, `COIL_INNER_HALF_WIDTH`, `COIL_BUILD`, `COIL_THICKNESS`, `COIL_MID_Y`, `SEARCH_COIL_FROM_CORNER`, `steel_law`).
- Produces: `@dataclass(frozen=True) class Team24Params` with those values as defaults plus `fillet: float = 0.0` (m, 3e-3 adds the 3 mm fillets), `end_clearance: float = 2e-3` (axial gap between the stack end face and the coil bridge), `air_radius_factor: float = 1.5` (outer air cylinder radius over `R_STATOR_OUT`), `air_end_factor: float = 1.0` (air beyond the coil bridge, in units of `R_STATOR_OUT`), `slab: bool = False`, `maxh: float = 4e-3`, `gap_maxh: float = 0.5e-3`. Every field may be overridden for the G1 perturbations.
- Produces: `team24_model(params: Team24Params = Team24Params()) -> Model3D`. Materials `steel` (stator and rotor), `air`, `shaft` (air law), `coil_0`, `coil_1` (series: same ampere-turns); faces `sym_z`, `outer`, `coil_<k>_in`, `coil_<k>_out`; an internal face `search` (the rotor pole section 8.7 mm from the corner along the flank, over the whole half stack); an air shell `gap_shell` between r = 51.6 mm and 53.2 mm (the 2D band radii) for the Arkkio torque. With `slab=True`: z ∈ [0, DEPTH/2], both z faces in `dirichlet` (`sym_z|end_z`), coil sides only (no bridge, the coil's two `_out` faces at the far z face), and no end air.
- Coil: each side is the fixture's 24 × 17 mm rectangle extruded from z = 0 to DEPTH/2 + `end_clearance` + `COIL_THICKNESS`; the bridge is a prism over the pole joining the two sides, from z = DEPTH/2 + `end_clearance` to that top, with the sides' radial (y) extent. Current direction as in the fixture: both coils push flux the same way through their poles.

- [ ] **Step 1: Write failing tests**
  - `test_iron_volume`: the steel volume equals the 2D fixture's iron area (`team24_fixture.team24_mesh()` triangle areas over steel) × DEPTH/2 within 0.5 % (the curved faces are meshed).
  - `test_regions_and_faces_present`: every material and face name above exists in the mesh, in both modes.
  - `test_fillet_changes_volume`: `fillet=3e-3` changes the steel volume by more than 0 and less than 2 %.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_team24_geometry.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `Team24Params` and `team24_model` in `tools/end3d/team24.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "end3d: TEAM 24 3D geometry, full and slab"`

### Task 5: Post-processing

**Files:**
- Create: `tools/end3d/post.py`
- Test: `tests/end3d/test_end3d_post.py`

**Interfaces:**
- Consumes: `Model3D`, `Solution3D`, `coil_current_density`.
- Produces (all full-machine values, the mirror factor 2 applied here and nowhere else):
  - `flux_linkage(model, sol, coils: Sequence[str], current: float, ampere_turns: Mapping[str, float]) -> float` — ψ = 2 ∫ A·J dV / current (Wb-turns), J the coils' ampere-turn density.
  - `arkkio_torque(model, sol, r_inner: float, r_outer: float, shell: str = "gap_shell") -> float` — T = 2 ∫_shell r B_r B_θ dV / (μ0 (r_outer − r_inner)), counter-clockwise positive (the srmcore convention).
  - `coenergy(model, sol) -> float` — 2 ∫ (B·H − w) dV (J).
  - `face_flux(model, sol, face: str) -> float` — 2 ∫_face B·n dA (Wb).

- [ ] **Step 1: Write failing tests** on the TEAM 24 slab at a coarse mesh (`maxh=8e-3`), linear steel (`LinearLaw` with μr 1000) so the tests are quick:
  - `test_slab_scales_with_depth`: slabs with `DEPTH` = D and 2D give full-machine ψ and torque in the ratio 2 within 0.2 % (a slab has no end effects, so both scale with length). The factor 2 against the 2D model itself is checked in G2 (Task 8).
  - `test_coenergy_equals_half_li_linear`: with linear materials, `coenergy` equals ½ · ψ · I within 0.5 %.
  - `test_torque_virtual_work`: the Arkkio torque equals the central difference of `coenergy` over a rotor rotation of ±0.5° within 2 % (linear, coarse mesh).
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_post.py -v`. Expected: FAIL. Mark the module `slow` if it runs over 30 s.
- [ ] **Step 3: Implement** the four functions in `tools/end3d/post.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "end3d: flux linkage, Arkkio shell torque, co-energy, face flux"`

### Task 6: G0 cost spike (gate)

**Files:**
- Create: `tools/end3d/g0_timing.py` (script, `python tools/end3d/g0_timing.py [--levels 4e-3 2.8e-3 2e-3] [--max-dofs N] [--json docs/validation/r4_g0.json]`)
- Create: `docs/r4-end-effect-results.md` (sections G0, G2, G1; spec §10 contents for later sections as headings marked "R4b")
- Test: `tests/end3d/test_end3d_g0.py`

**Interfaces:**
- Consumes: `team24_model`, `solve3d`, post functions.
- Produces: JSON `{"host": ..., "levels": [{"maxh": m, "ndof": n, "seconds": s, "newton_iterations": k, "peak_rss_bytes": b, "converged": bool, "torque": t, "psi": p, "skipped": bool}], "sweep_estimate_hours": h}`, written after each level. `sweep_estimate_hours` = the finest converged level's seconds × the R4b sweep size from spec §6 minimums (4 machines × 4 stacks × 7 angles × 3 currents = 336 solves) / 3600. Geometry variants (decision 6) multiply this; the report states the multiplier as unknown until R4b.

- [ ] **Step 1: Write failing test** `test_skips_level_over_max_dofs` (fast; monkeypatch the solver to a stub returning a fixed `Solution3D`): with `--max-dofs 1`, every level is recorded with `skipped: true`, the JSON is valid after each level, and the script exits 0.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_g0.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the script.
- [ ] **Step 4: Run** the test. Expected: PASS.
- [ ] **Step 5: Run G0** on the LattePanda: `python tools/end3d/g0_timing.py --json docs/validation/r4_g0.json` (background). Fill the G0 section of `docs/r4-end-effect-results.md`.
- [ ] **Step 6: Gate.** If one solve does not fit in RAM, or `sweep_estimate_hours` × 1 (no variants) exceeds 168 h (one week), stop and report to the owner with the numbers (spec G0: shrink the sweep, then re-plan). Otherwise continue.
- [ ] **Step 7: Commit** `git commit -m "end3d: G0 timing spike and results"`

### Task 6b: Swept prism mesh (added 2026-11-04 after G0 failed on RAM)

G0 showed the free-tetrahedral TEAM 24 model fits in 30 GB only up to about 3 M DOFs (12 mm / 1.5 mm gap), because the fine gap cells repeat through the whole height (`docs/r4-end-effect-results.md`). The owner chose a swept (layered) mesh, as COMSOL's 3D rotating-machine guide recommends: a fine 2D cross-section mesh stacked in z layers, thin near the stack end and thick mid-stack; end turns are a different material in the end layers. The solver (Task 3) and post-processing (Task 5) do not change.

**Files:**
- Create: `tools/end3d/swept.py`
- Modify: `tools/end3d/team24.py` (a swept builder beside the tetrahedral one), `tools/end3d/g0_timing.py` (levels for the swept model)
- Test: `tests/end3d/test_end3d_swept.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Layers: z: tuple[float, ...]` (increasing layer boundaries from 0) and `graded_layers(z_end: float, z_top: float, h_end: float, h_mid: float, ratio: float = 1.3, breaks: Sequence[float] = ()) -> Layers`. The spacing is `h_end` at z_end (the stack end), grows by at most `ratio` per layer towards z = 0 and towards z_top, is capped at `h_mid`, and puts a boundary exactly on z_end and on every value in `breaks` (coil bridge bottom and top).
- Produces: `swept_mesh(section: netgen 2D mesh with named regions and named edges, layers: Layers, material: Callable[[str, int], str | None], faces: Callable[[str, int], str | None], bottom: Callable[[str], str], top: Callable[[str], str | None]) -> ngsolve.Mesh`. Each 2D triangle becomes one prism per layer. `material(region2d, k)` names the 3D material of that region in layer k (None leaves the cell out, so the mesh may end at the stator outer surface in slab mode). `faces(edge2d, k)` names the vertical boundary or internal faces swept from a named 2D edge in layer k (None: no boundary element). `bottom(region2d)` names the z = 0 face of each region (`sym_z` or a coil `_in`/`_out`). `top(region2d)` names the top face (`outer`, `end_z` or a coil face; None where the column ends lower). Faces between cells of different material get no boundary element unless `faces` names them (internal faces such as `search`).
- Produces: `team24_swept_model(params: Team24Params, h_gap: float, h_iron: float, h_end: float, h_mid: float) -> Model3D` with the same material, face and coil names as `team24_model` (so `ampere_turns`, `rotor_pole_flux` and every post function work unchanged). The 2D section is built with `netgen.occ` in 2D (WorkPlane faces, `OCCGeometry(..., dim=2)`), with local mesh size `h_gap` on the gap shell and the pole faces bordering it, and `h_iron` elsewhere; it includes as separate regions the bridge footprint (split into its steel and air parts) and, in full mode, the outer air out to `air_radius_factor`·R_STATOR_OUT; the search chord is a named internal 2D edge. Full mode: stack layers z ∈ [0, DEPTH/2] carry the 2D materials; end layers up to z_top carry air, except coil sides (continuing to the bridge top), the bridge footprint in the bridge layers (the coil) and the gap shell (all layers, ruling R15). Slab mode: stack layers only, `end_z` on top, no cells outside R_STATOR_OUT (ruling R13).

- [ ] **Step 1: Write failing tests**
  - `test_graded_layers`: boundaries are increasing, include z_end and every break exactly, the spacing at z_end is h_end within 1 %, no step exceeds `ratio` × its neighbour, none exceeds h_mid.
  - `test_swept_volumes_match_tet_model`: for full and slab TEAM 24 at a coarse setting, the volume of each material equals the tetrahedral `team24_model`'s within 0.5 %.
  - `test_swept_faces_complete`: every boundary element at z = 0 is `sym_z` or a coil face; in slab mode every element at z = DEPTH/2 is `end_z` or a coil `_out`; `search` exists with area 25.4 × 12.7 mm within 0.5 %; in full mode the coils' `_in`/`_out` currents are ±AT (`coil.face_current`).
  - `test_swept_matches_tet_linear` (slow): linear steel (μr 1000) at 5 A, coarse: swept and tetrahedral models agree on ψ and Arkkio torque within 1 %, full and slab.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/end3d/test_end3d_swept.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `swept.py` and `team24_swept_model`; switch `g0_timing.py` to the swept model, a level being `(h_gap, h_iron, h_end, h_mid)` with defaults (1.0, 4.0, 1.0, 3.0), (0.7, 3.0, 0.7, 2.0), (0.5, 2.0, 0.5, 1.5) mm; record the layer count and prism count per level.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "end3d: swept prism mesh for TEAM 24"`
- [ ] **Step 6: Re-run G0** (Task 6 Steps 5–7) with the swept levels; same gate.

Tasks 7, 8 and 9 use the swept builder: Task 7's `radial_model` builds its 2D section from the srmcore outline and calls `swept_mesh`; Tasks 8 and 9 use `team24_swept_model`. The tetrahedral `team24_model` stays as the cross-check of Task 6b's tests.

### Task 7: Radial machine 3D geometry

**Files:**
- Create: `tools/end3d/radial.py`
- Test: `tests/end3d/test_end3d_radial_geometry.py`

**Interfaces:**
- Consumes: `srmcore.topology.radial.parametric_outline`, `srmcore.maps.end_winding.coil_geometry`, `srmcore.materials.library_law`, `Design` from `conftest.make_8_6`.
- Produces: `radial_model(design: Design, angle: float, phase: str = "A", slab: bool = False, maxh: float | None = None, gap_maxh: float | None = None, end_clearance: float | None = None, air_radius_factor: float = 1.5, air_end_factor: float = 1.0) -> Model3D`. Stator and rotor iron are the outline's 2D faces built as `netgen.occ` wires (lines and arcs from the outline segments, no resampling), extruded over z ∈ [0, stack_length/2]; the rotor is rotated by `angle` (phase A aligned at 0, counter-clockwise positive). Materials take the design's `RegionMaterials` (stator, rotor, shaft) through `library_law`; laminated iron uses the processed law (stacking factor already applied by `process_bh`). Only the excited phase's coils are built: for each of its poles, the two `CoilSide` polygons extruded to stack_length/2 + `end_clearance` + `coil_geometry(...).build`, joined by a bridge prism over the pole. `end_clearance` defaults to `slot_liner_thickness`. `gap_shell` is the band annulus (`band_inner_radius` to `band_outer_radius`). `maxh` and `gap_maxh` default to the design's `full` preset sizes from `resolve_mesh_settings`. Slab mode as in Task 4. Imported iron (`machine.iron` set) raises `NotImplementedError` (R4 covers parametric machines).

- [ ] **Step 1: Write failing tests** on `make_8_6()`:
  - `test_iron_volumes`: stator and rotor iron volumes equal the outline's 2D areas (as `srmapp.sizing.estimates` computes them, or the `full` static mesh's areas) × stack_length/2 within 0.5 %.
  - `test_rotor_rotation`: at `angle = π/6` the rotor volume is unchanged and the rotor's centroid moment matches the rotated 2D one within 1e-6 m.
  - `test_only_excited_phase_coils`: 2 coils for the 8/6 phase A, named `coil_0`, `coil_1`.
  - `test_imported_iron_refused`: a design with `iron` set raises `NotImplementedError`.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_radial_geometry.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `radial_model` in `tools/end3d/radial.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "end3d: radial machine 3D geometry from the srmcore outline"`

### Task 8: G2, 3D slab equals 2D (gate)

**Files:**
- Create: `tools/end3d/g2_slab.py` (`python tools/end3d/g2_slab.py [--json docs/validation/r4_g2.json]`)
- Test: `tests/end3d/test_end3d_g2.py` (slow)

**Interfaces:**
- Consumes: `radial_model(..., slab=True)`, `team24_model(Team24Params(slab=True))`, `solve3d`, post; 2D references: `srmcore.maps.point.solve_point` on the `full` mesh of `make_8_6()` (NGSolve 2D adapter), and `team24_fixture.locked_rotor_map(NgsolveAdapter(), currents=(7.41,))`.
- Produces: JSON rows `{machine, angle, current, psi_3d, psi_2d, psi_rel, torque_3d, torque_2d, torque_rel_peak, converged}`; `torque_rel_peak` = |T3D − T2D| / peak |T2D| over the rows of that machine.

Points: 8/6 at 20 A, phase A, angles 0 (aligned), the half-overlap angle and π/N_r (unaligned); TEAM 24 at 7.41 A. Signed comparisons (Review Focus 3). Pass: every row converged, `psi_rel` ≤ 0.005 and `torque_rel_peak` ≤ 0.01. If the 3D mesh is not fine enough to reach that, refine (smaller `maxh`/`gap_maxh`) within `--max-dofs`; record the level used. A failure means a 3D-model bug: fix it before Task 9 (spec G2).

- [ ] **Step 1: Write the slow test** `test_g2_slab_matches_2d`: runs the script's point function for the 8/6 aligned point and the TEAM 24 point, asserts the pass rule above and that the signs of torque and ψ match 2D.
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_g2.py -v -m slow`. Expected: FAIL (script missing).
- [ ] **Step 3: Implement** `tools/end3d/g2_slab.py`.
- [ ] **Step 4: Run G2** in full: `python tools/end3d/g2_slab.py --json docs/validation/r4_g2.json` (background). Then the slow test. Expected: PASS. Fill the G2 section of the results doc.
- [ ] **Step 5: Commit** `git commit -m "end3d: G2 slab vs 2D check and results"`

### Task 9: G1, 3D TEAM 24 vs measurement (gate)

**Files:**
- Create: `tools/end3d/g1_team24.py` (`python tools/end3d/g1_team24.py [--max-dofs N] [--json docs/validation/r4_g1.json]`)
- Test: `tests/end3d/test_end3d_g1.py` (fast, on a stubbed solver: the budget arithmetic and the verdict)

**Interfaces:**
- Consumes: `team24_model`, `Team24Params`, `solve3d`, post; measured values from `team24_fixture`: torque `TABLE_TORQUE[-1]` (3.22 N·m), flux `TABLE_ROTOR_FLUX[-1]` (4.72e-4 Wb), current 7.41 A (`TABLE_CURRENT[-1]`).
- Produces: `budget(nominal: dict[str, float], perturbed: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]` (row → {"torque": rel, "flux": rel}) and `verdict(nominal, measured, budget) -> dict` with `{"torque": {"error_rel", "budget_rel", "pass"}, "flux": {...}, "pass": bool}`. Rows sum worst-case, as `srmcore.maps.validation.UncertaintyBudget` does.

Budget rows, each from 3D runs (spec G1), perturbation sizes fixed here before any run:

| Row | Runs | Value |
|---|---|---|
| mesh | nominal at 3 `maxh` levels (each `gap_maxh` scaled with it) | \|finest − Richardson extrapolation\| / finest; if the levels are not monotone, \|finest − next\| |
| air box | `air_radius_factor` 1.5 → 2.25 and `air_end_factor` 1.0 → 1.5 | \|change\| |
| material | `steel_law(js)` at Js × 1.02 (`ASSUMED_JS` nominal); × 0.98 is below the B-H data, so as in `maps.validation` the row is one-sided (2026-11-05, before any run). No grade allowance: rows come from 3D runs only | \|change\| |
| table rounding | none | ±0.005 / measured (0.16 % torque, 0.11 % flux) |
| fillets | `fillet` 0 → 3e-3 | \|change\| |
| figure dimensions | hub radius and yoke thickness each ±0.5 mm | half spread, each its own row |
| search coil | `SEARCH_COIL_FROM_CORNER` ±1 mm | half spread (flux only) |
| coil end | `end_clearance` 1 mm and 5 mm (nominal 2 mm) | half spread |

Pass (spec G1): for torque and for flux, |3D − measured| / measured ≤ the row sum. Write the nominal 3D values, the rows, the errors and the verdict to the JSON after each run (Review Focus 4). Also record the 3D end-turn share: ψ(full) − ψ(slab) at 7.41 A beside the analytic `team24_fixture.end_winding_inductance(1.5) × 7.41` (the hook check, spec §4).

- [ ] **Step 1: Write failing tests** with a stub: `test_budget_sums_rows` (known perturbed values give known rows and sum), `test_verdict_pass_and_fail` (error just inside and just outside the sum), `test_nonconverged_run_refused` (a perturbed run with `converged=False` makes `verdict` raise `ValueError` naming the row).
- [ ] **Step 2: Run** `python -m pytest tests/end3d/test_end3d_g1.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `budget`, `verdict` and the script.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Run G1**: `python tools/end3d/g1_team24.py --json docs/validation/r4_g1.json` (background; hours).
- [ ] **Step 6: Record**: fill the G1 section of `docs/r4-end-effect-results.md` (table: measured, 2D, 3D, error, each budget row, sum, verdict; the end-turn share against the hook), add a dated entry to core spec §11 with the verdict, update the wiki Progress tab (R4 row and a new row for whichever of R4b-fit or R4b-fail comes next) and the project doc (R4 section and milestone row).
- [ ] **Step 7: Commit** `git commit -m "end3d: G1 TEAM 24 3D vs measurement, verdict"`, push the branch, open the PR, wait for CI green, merge.

## After R4a

- G1 pass → write plan R4b: G3, the §6 sweep (with G0's cost), the correction form fit (§5) and G4, `srmcore/maps/end_effect.py` and its hook sites, the budget row, the evaluation record, UI chips, G5, the ranking bias (§8), and the version bumps.
- G1 fail → write plan R4b-fail: spec decision 3 (measured gap into the `end_effect` row by decision 7's rule, results recorded, tracker item for the cause hunt), then R5.
