# R2 DXF Round Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a case's laminations as DXF, import an edited DXF (iron only), check it, mesh and map it with the same engine, and compare before/after in the web app.

**Architecture:** The imported iron is a frozen model `ImportedIron` on `RadialSRMParams.iron` (omitted from JSON when None, so existing hashes do not change). `topology/radial.build_outline` swaps the parametric iron contours for the imported ones; `geometry/build.py` cuts holes and groove air. DXF I/O and the import checks live in `topology/dxf_io.py` and `topology/imported.py`. srmweb adds export, import and compare routes; the web case page adds the buttons, an import dialog and a before/after table.

**Tech Stack:** Python 3.12+, pydantic ≥ 2.11 (`exclude_if`), ezdxf (MIT), Gmsh OCC, FastAPI, React 19 + Vite + vitest.

**Spec:** `docs/superpowers/specs/2026-10-15-r2-dxf-round-trip-design.md` (read §11 rulings first: they amend §3, §4, §7 and §9).

## Global Constraints

- Only the iron comes from the DXF. Coils, winding, band radii, end-winding geometry and refinement features stay parametric.
- All lengths in SI (metres) inside srmcore; DXF files are mm.
- Tolerances: loop joins 1 µm; repeat check 1 µm; spline chord error ≤ 1 µm; canonical rounding 0.1 µm; snapping to the bore, rotor, stator-OD and shaft circles (and arc centres to the origin) within 1 µm.
- Minimum web width: `srmcore.model.validator.min_web_width(p)` = max(1 mm, 2 × lamination thickness).
- Edits repeat every 2π/Ns (stator) and 2π/Nr (rotor); refusal message names the rule, the place, and the polar-array fix.
- A parametric design (iron None) builds, meshes, hashes and serialises exactly as before; `tests/maps/test_goldens.py` stays green.
- Only `topology/dxf_io.py` imports ezdxf. `topology` imports only `model`. srmweb never imports gmsh/ngsolve/netgen/skfem.
- Every iron problem is a `srmcore.model.errors.ValidationIssue(parameter="iron", rule, message, severity)`; locations in the message are in mm, `(x, y)` with one decimal.
- No blue in `web/src` (`noBlue.test.ts`); `web/src/api/schema.ts` is generated, never hand-edited.
- Versions at the end: srmcore, srmapp, srmweb, `web/` 0.5.0. `"0.5.0"` is NOT added to `VALIDATED_VERSIONS` in this plan.

## Review Focus

1. A DXF from Onshape whose coordinates are a few 1e-7 mm off the parametric circles: must snap, not leave sliver rings at the bore or OD (test in Task 3: `test_snaps_near_circle_vertices`).
2. A setup file or raw API input carrying `iron` that never went through DXF import: must be checked the same way (test in Task 6: `test_check_case_runs_iron_checks`).
3. Editing geometry parameters on a DXF case through the API (bypassing the locked form): the iron checks against the new parameters must refuse it (test in Task 6: `test_patch_params_on_dxf_case_rechecks`).
4. A full DXF CIRCLE or an arc ≥ π (`Arc` must be a minor arc): must be split into minor arcs (test in Task 4: `test_circle_and_major_arc_split`).
5. Importing the same file twice: same canonical iron, same map cache entry (test in Task 4: `test_reimport_is_canonical`).

---

### Task 1: Iron model and dependencies

**Files:**
- Create: `src/srmcore/model/iron.py`
- Modify: `src/srmcore/model/design.py` (field on `RadialSRMParams`), `pyproject.toml` (`pydantic>=2.11`, add `ezdxf>=1.3` to `dependencies`)
- Test: `tests/model/test_iron_model.py`

**Interfaces:**
- Produces: `IronLine(kind="line", start: tuple[float, float], end: tuple[float, float])`, `IronArc(kind="arc", start, end, center)` (minor arc, as `topology.primitives.Arc`), `IronSegment` (discriminated on `kind`), `IronLoop = tuple[IronSegment, ...]`, `ImportedIron(stator_outer: IronLoop, stator_bore: IronLoop, stator_holes: tuple[IronLoop, ...] = (), rotor_outer: IronLoop, rotor_bore: IronLoop, rotor_holes: tuple[IronLoop, ...] = ())`, all frozen, `extra="forbid"`. `RadialSRMParams.iron: ImportedIron | None = Field(None, exclude_if=lambda v: v is None)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_parametric_json_unchanged():
    d = make_8_6()
    assert "iron" not in d.to_json()
    assert design_hash(d) == design_hash(Design.from_json(d.to_json()))

def _ring(r):   # a full circle as 4 quarter arcs, the test's stand-in for every contour
    pts = [(r, 0.0), (0.0, r), (-r, 0.0), (0.0, -r)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(0.0, 0.0)) for i in range(4))

IRON = ImportedIron(stator_outer=_ring(0.05), stator_bore=_ring(0.03), rotor_outer=_ring(0.029),
                    rotor_bore=_ring(0.008), rotor_holes=(_ring(0.001),))

def test_iron_round_trips_json():
    p = make_8_6().machine.model_copy(update={"iron": IRON})
    assert RadialSRMParams.model_validate_json(p.model_dump_json()) == p

def test_iron_changes_hash():
    d = make_8_6()
    d2 = d.model_copy(update={"machine": d.machine.model_copy(update={"iron": IRON})})
    assert design_hash(d2) != design_hash(d)
```

(`_ring` is model-level only; the model does not check geometry, Task 3 does.)

Also pin the current hash of `make_8_6()` as a literal (compute it on main before the change) so a later serialisation change is caught.

- [ ] **Step 2: Run** `python -m pytest tests/model/test_iron_model.py -v` → FAIL (import error).
- [ ] **Step 3: Implement** `model/iron.py` and the field. `pip install -e ".[dev,ngsolve,web]"` to pull ezdxf.
- [ ] **Step 4: Run** the new tests, then `python -m pytest -m "not slow" tests/model tests/maps -q` → PASS.
- [ ] **Step 5: Commit** `feat(model): ImportedIron on RadialSRMParams`.

### Task 2: Outline and geometry accept imported iron

**Files:**
- Modify: `src/srmcore/topology/radial.py`, `src/srmcore/geometry/build.py`, `src/srmcore/mesh/static.py:158-180`, `src/srmcore/mesh/settings.py:57-73`
- Create: `src/srmcore/topology/imported.py` (only `parametric_iron`, `to_segments` here; checks come in Task 3)
- Test: `tests/geometry/test_imported_geometry.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces:
  - `topology.imported.parametric_iron(p: RadialSRMParams) -> ImportedIron`: the parametric contours (stator OD and shaft circle as 4 quarter arcs starting at angle 0), ignoring `p.iron`.
  - `topology.imported.to_segments(loop: IronLoop) -> tuple[Segment, ...]` and `from_segments(segs) -> IronLoop`.
  - `RadialOutline` new fields with defaults: `stator_outer_boundary: tuple[Segment, ...] | None = None`, `stator_holes: tuple[tuple[Segment, ...], ...] = ()`, `rotor_inner_boundary: tuple[Segment, ...] | None = None`, `rotor_holes: tuple[tuple[Segment, ...], ...] = ()`.
  - `GeometryModel.outer_boundary_curves: tuple[int, ...]` and `stator_outer_curves: tuple[int, ...]` (replace the single-int fields).
  - New air regions `stator_hole_air` (stator part) and `rotor_hole_air` (rotor part): kind `air`, size key `slot_air`.
  - Refinement tag `iron_detail` with size `(max(min_web_width(p) / 2, gap), growth)`, set only when `p.iron` is set.

- [ ] **Step 1: Write the failing tests**
  - `test_parametric_outline_unchanged`: for each `reference_design`, `build_outline(p)` has the new fields at their defaults.
  - `test_parametric_iron_matches_outline`: `to_segments(parametric_iron(p).stator_bore)` equals `build_outline(p).stator_inner_boundary` geometrically (same points within 1e-12).
  - `test_rotor_hole_meshes`: 8/6 with `iron = parametric_iron(p)` plus 6 rotor holes (circles of r 2 mm at radius `(shaft_radius + rotor_yoke_outer_radius)/2`, every 60°); `build_machine_mesh` succeeds; total `rotor_hole_air` area = 6π(2 mm)² within 1 %; `rotor_iron` area drops by the same.
  - `test_yoke_groove_keeps_od_dirichlet`: 8 V-grooves (1 mm deep, 2 mm wide) on the stator OD, every 45°; mesh succeeds; every `outer_edges` node lies at `stator_outer_radius` within 1e-9; `stator_hole_air` area = 8 × 1 mm² within 1 %.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `build_outline(p)`: compute the parametric outline as now; when `p.iron` is set, replace `stator_inner_boundary` and `rotor_outer_boundary` with the imported bore/outer loops, set the four new fields, and add `iron_detail` = every imported segment whose endpoints do not both match (1 µm) a segment of `parametric_iron(p)`, plus all hole segments. Coil sides and other refinement features stay parametric.
  - `build_geometry`: stator iron = surface(stator outer contour or OD circle, minus bore contour and stator holes); `stator_hole_air` = `_disk(stator_outer_radius)` cut by the stator-outer surface, plus the hole surfaces; rotor iron = rotor outer surface minus rotor bore surface and rotor holes; `rotor_hole_air` = rotor-bore surface cut by the shaft disk, plus the hole surfaces; shaft stays `_disk(shaft_radius)`. Omit empty regions from `named`. Outer curves: every boundary curve of the union stator_iron + stator_hole_air whose points lie on the OD circle (bbox and `getValue` midpoint radius within `tol`).
  - `mesh/static.py`: `_edges` takes a tuple of curves and stacks them.
  - `ROTOR_REGIONS` gains `rotor_hole_air`.
- [ ] **Step 4: Run** the new tests and `python -m pytest -m "not slow" tests/geometry tests/mesh tests/topology -q` → PASS.
- [ ] **Step 5: Commit** `feat(geometry): build meshes from imported iron contours`.

### Task 3: Iron canonicalisation and checks

**Files:**
- Modify: `src/srmcore/topology/imported.py`, `src/srmcore/topology/radial.py` (raise on failed checks)
- Test: `tests/topology/test_iron_checks.py`

**Interfaces:**
- Consumes: Task 2 helpers.
- Produces:
  - `iron_from_loops(loops: list[tuple[Segment, ...]], p: RadialSRMParams) -> tuple[ImportedIron | None, list[ValidationIssue]]`: drops loops matching a parametric coil side (1 µm), classifies the rest (spec §5.4), canonicalises (below), then runs `check_iron`. Iron is None when any issue is an error.
  - `check_iron(p: RadialSRMParams) -> list[ValidationIssue]`: checks §5.3 and §5.5–5.8 on `p.iron` against `p`'s parameters; rules `centre`, `rotor_angle`, `bodies`, `stray_loop`, `air_gap`, `coil_overlap`, `repeat`, `web_width`.
  - `build_outline(p)` raises `InputError(errors)` when `check_iron(p)` returns errors.

Canonical form: round every coordinate to 1e-7 m; snap arc centres within 1 µm of the origin to (0, 0); project vertices within 1 µm of the bore, rotor, stator-OD or shaft circle radially onto it; orient each loop counter-clockwise; start each loop at its vertex with the smallest (angle in [0, 2π), radius); sort holes by their start vertex.

Check details not fixed by the spec:
- `rotor_angle`: the rotation in (−π/Nr, π/Nr] that best maps the parametric rotor-outer vertices onto the imported contour (sampled every 0.5° of rotor pitch, then refined) must be 0 within 1e-4 rad.
- `coil_overlap`: iron closer than `slot_liner_thickness / 2` to any coil side is an error.
- `repeat`: sample each iron contour (`sample_segment`, step 0.1 mm); every sample rotated by 2π/Ns (stator) or 2π/Nr (rotor) lies within 1 µm of the same body's boundary. Report the first failing sample's location and how many times its feature repeats (count of rotations k·2π/N for which the sample still lies on the boundary).
- `web_width`: on the sampled boundary (0.1 mm step), the smallest distance between two samples that are not within 3 samples of each other along the same loop, whose midpoint lies inside iron; error when < `min_web_width(p)`, reporting the midpoint.
- Messages, verbatim pattern for `repeat`: `"Stator edit near ({x:.1f}, {y:.1f}) mm repeats {k} times; it must repeat every {deg:g}° ({n} times on this {Ns}/{Nr} stator). Draw it once and polar-array it {n}× around the centre."` (rotor: "rotor", Nr).

- [ ] **Step 1: Write the failing tests** (each builds loops in metres from `parametric_iron` plus an edit, then asserts the rule and the location substring):
  - `test_parametric_iron_passes`: `check_iron` on `parametric_iron(p)` returns [] for every `reference_design`.
  - `test_snaps_near_circle_vertices`: perturb every bore vertex radially by +0.3 µm; after `iron_from_loops`, every pole-face vertex has radius exactly `bore_radius` (to 1e-15).
  - `test_coil_loops_dropped`: loops = iron + all coil sides → same iron as without them.
  - `test_shifted_centre`, `test_rotated_rotor` (rotor turned 2°), `test_iron_in_air_gap` (a stator pole face pushed 0.1 mm into the gap), `test_iron_in_coil`, `test_two_grooves_refused` (message contains "repeats 2 times" and "polar-array it 8×"), `test_eight_grooves_pass`, `test_thin_web` (a hole 0.5 mm from the OD on a 0.1 mm lamination design: min web 1 mm), `test_stray_loop`, `test_two_rotor_pieces`.
  - `test_build_outline_raises`: `build_outline` on params whose iron has a 2-groove stator raises `InputError` with rule `repeat`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** in `topology/imported.py` (pure Python + numpy; no new dependency).
- [ ] **Step 4: Run** the tests and the Task 2 tests → PASS.
- [ ] **Step 5: Commit** `feat(topology): canonical imported iron and import checks`.

### Task 4: DXF read and write

**Files:**
- Create: `src/srmcore/topology/dxf_io.py`
- Modify: `tests/test_import_rules.py` (ezdxf allowed only in `topology/dxf_io.py`)
- Test: `tests/topology/test_dxf_io.py`

**Interfaces:**
- Consumes: `parametric_iron`, `iron_from_loops`, `to_segments`.
- Produces:
  - `write_dxf(p: RadialSRMParams) -> bytes`: R2010, `$INSUNITS` = 4 (mm), layers `STATOR`, `ROTOR`, `COILS`; iron from `p.iron` or `parametric_iron(p)`; a loop that is a full origin-centred circle is written as one CIRCLE; other segments as LINE/ARC; coil sides on `COILS`.
  - `read_loops(data: bytes) -> tuple[list[tuple[Segment, ...]], list[ValidationIssue]]`: spec §5.1–5.2 (rules `dxf_units`, `dxf_flat`, `dxf_entity`, `open_loop`, `overlap`, `self_intersection`); converts to metres; splits CIRCLEs and arcs ≥ π into minor arcs; flattens SPLINE with `ezdxf` `flattening(distance=1e-3)` (mm, i.e. 1 µm); explodes INSERT; bulge polylines via `ezdxf.math.bulge_to_arc`.
  - `import_dxf(data: bytes, p: RadialSRMParams) -> tuple[ImportedIron | None, list[ValidationIssue]]`: `read_loops` then `iron_from_loops`; adds the warning rule `iron_area` when the iron area differs from `p`'s current iron (imported or parametric) by more than 10 %.

- [ ] **Step 1: Write the failing tests** (DXFs made with ezdxf in the test, in mm):
  - `test_round_trip_parametric`: `import_dxf(write_dxf(p), p)` gives `parametric_iron`-equivalent iron (same canonical loops) and no issues, for each `reference_design`.
  - `test_reimport_is_canonical`: import → set iron → `write_dxf` → import again: identical `ImportedIron`, identical `design_hash`.
  - `test_circle_and_major_arc_split`: a 300° ARC and a CIRCLE come back as minor arcs.
  - `test_inch_converted`, `test_unknown_units_refused` (`$INSUNITS` codes accepted: 0 none → mm, 1 inch, 4 mm, 6 m; every other code refused, e.g. 5 cm, with rule `dxf_units`), `test_non_flat_refused`, `test_open_loop_reported` (location in mm), `test_unsupported_entity` (an ELLIPSE → rule `dxf_entity`, message names "ELLIPSE"), `test_spline_flattened` (a spline on a hole edge; chord error ≤ 1 µm), `test_bulge_polyline`, `test_z_offset_ignored` (everything at z = 5), `test_text_ignored`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests and `python -m pytest tests/test_import_rules.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(topology): DXF export and import`.

### Task 5: Engine end to end on imported shapes, mass

**Files:**
- Modify: `src/srmapp/sizing/estimates.py` (`_iron_areas` uses `p.iron` when set)
- Test: `tests/maps/test_imported_solve.py`, `tests/app/test_imported_mass.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `active_mass(p)` with imported iron: stator and rotor areas from the imported loops (polygon area of the sampled loop with arcs integrated exactly, holes subtracted).

- [ ] **Step 1: Write the failing tests**
  - `test_no_edit_point_matches` (screening 8/6, `solve_point` at the aligned angle and I_max = 20 A, plus at a mid angle): design with `iron = import_dxf(write_dxf(p), p)[0]` vs the parametric design: ψ within 1e-5 relative, torque within 1e-4 × |peak|.
  - `test_rotor_holes_lower_mass`: 6 holes of r 2 mm → rotor iron mass drops by 6π(2 mm)² × stack × density × stacking factor within 1e-9 relative; La (from `solve_point` at aligned, 5 % of I_max) changes by less than 2 %.
  - `test_yoke_grooves_lower_psi`: 8 grooves 1 mm deep → ψ at aligned, I_max is lower than parametric, by less than 3 %.
- [ ] **Step 2: Run** → FAIL (mass test), the solve tests may already pass; keep them.
- [ ] **Step 3: Implement** the area change.
- [ ] **Step 4: Run** the tests and `python -m pytest -m "not slow" tests/app -q` → PASS.
- [ ] **Step 5: Commit** `feat(app): mass from imported iron; end-to-end imported solves`.

### Task 6: Web API

**Files:**
- Modify: `src/srmweb/api.py`, `src/srmweb/cases.py` (`check_case`), `src/srmweb/store.py` (`CASE_ORIGINS` += `"dxf"`), `src/srmweb/geometry.py` (draw free contours and holes), `src/srmweb/schemas.py` (`CompareOut`, `CompareRowOut`), `web/openapi.json`, `web/src/api/schema.ts` (regenerated)
- Test: `tests/web/test_dxf_routes.py`

**Interfaces:**
- Consumes: `write_dxf`, `import_dxf`, `check_iron`, `active_mass`.
- Produces:
  - `GET /api/cases/{id}/dxf` → `application/dxf` attachment `<label>.dxf`.
  - `POST /api/cases/{id}/dxf` (multipart file field `file`, ≤ 10 MB; 413 above) → 201 `DxfImportOut{case: CaseOut, warnings: list[{loc, msg}]}` for a new stale case (origin `dxf`, `parent_case_id` = id, label `"DXF edit of <parent label>"`, parent inputs with `design.machine.iron` set); 422 in the existing `_invalid` shape with every error at `loc ["iron"]`.
  - `GET /api/cases/{id}/compare` → `CompareOut{parent_id: str | None, parent_evaluated: bool, rows: list[CompareRowOut{name, unit, before: float | None, after: float | None}]}`; rows in order: La (mH), Lu (mH), peak torque (N·m), ψ_max (Wb), stator iron (kg), rotor iron (kg), total mass (kg). Key numbers from each case's evaluation; masses from `active_mass` on each case's reference design plus the evaluation's chosen winding copper (total = `mass_kg`). 404 when the case has no parent.
  - `check_case`: when `machine.iron` is set, `check_iron` errors at `loc ["design", "machine", "iron"]`.
- [ ] **Step 1: Write the failing tests** (FastAPI TestClient, as the existing web tests do): export returns a DXF that `import_dxf` reads cleanly; import of an 8-groove file creates a linked stale case; import of a 2-groove file → 422 with a `repeat` message; `test_check_case_runs_iron_checks` (a raw case with a bad iron → error at the iron loc); `test_patch_params_on_dxf_case_rechecks` (PATCH inputs changing `air_gap` on a DXF draft → the next `/api/validate` or evaluate refuses with an iron error); compare on a case without a parent → 404; compare with an unevaluated parent → `parent_evaluated` false and `before` all None; geometry SVG of a DXF case contains one path per hole.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**, then regenerate: `python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`.
- [ ] **Step 4: Run** `python -m pytest -m "not slow" tests/web -q` → PASS.
- [ ] **Step 5: Commit** `feat(web): DXF export, import and compare routes`.

### Task 7: Web UI

**Files:**
- Create: `web/src/components/case/DxfImportDialog.tsx`, `web/src/components/case/BeforeAfterTable.tsx`, `web/src/lib/compare.ts`, `web/src/lib/compare.test.ts`, `web/src/components/case/DxfImportDialog.test.tsx`
- Modify: `web/src/components/case/CaseActions.tsx` (Export DXF, Import DXF), `web/src/components/case/DimensionTab.tsx` (read-only when `inputs.design.machine.iron`), `web/src/pages/CasePage.tsx` (table above the analysis tabs when `parent_case_id` and origin `dxf`)

**Interfaces:**
- Consumes: Task 6 routes via `api`/`apiBlob` in `web/src/api/client.ts`.
- Produces: `compareRows(rows: CompareRow[]) -> {name, unit, before, after, delta, deltaPct}[]` in `lib/compare.ts` (`deltaPct` null when before is 0 or null).

- [ ] **Step 1: Write the failing tests** (vitest): `compareRows` deltas and nulls; the dialog lists every 422 message and does not navigate; on success it navigates to the new case. DimensionTab inputs are disabled with a note "Geometry comes from the imported DXF. Edit the parent case and import again to change it."
- [ ] **Step 2: Run** `cd web; npx vitest run` → FAIL.
- [ ] **Step 3: Implement.** Import sets `show_in_graphs` on both cases when fewer than 6 are shown. Unevaluated parent: the table shows "Parent not evaluated" and an Evaluate button for the parent.
- [ ] **Step 4: Run** `npx vitest run` and `npm run build` → PASS. Visual check on `srmweb-smoke` (export, import a groove DXF, table) with a screenshot.
- [ ] **Step 5: Commit** `feat(web): DXF buttons, import dialog, before/after table`.

### Task 8: Versions, bench, docs

**Files:**
- Modify: `pyproject.toml`, `src/srmcore/__init__.py`, srmapp/srmweb versions, `web/package.json` (all 0.5.0); `bench/requirements.in` (+ `ezdxf>=1.3`), `bench/requirements.lock` (regenerated with the pinned uv: `uv pip compile --universal --generate-hashes`), `bench/srmbench/reference/points_8_6.json` and `goldens_8_6.json` (regenerated with the commands in their modules' docstrings), `CLAUDE.md` (R2 state, DXF modules, routes), `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md` (R2 boxes).
- Test: `bench\run.bat --self-test`; `python -m pytest -m "not slow" -q` (whole fast suite); `python -m pytest tests/maps/test_goldens.py -q` (slow, must pass unchanged).

- [ ] **Step 1:** Bump versions; run the whole fast suite and the goldens test → PASS.
- [ ] **Step 2:** Update the bench lock and references; `bench\run.bat --self-test` → PASS; `bench\run.bat --tier quick --label r2-check --yes --keep --no-push` shows correctness pass (delete the `results/r2-check` folder after).
- [ ] **Step 3:** Docs as listed. Commit `chore: 0.5.0, bench lock and references, docs`.

### Owner steps after the merge (not for implementers)

1. Done check: export the 8/6 case, in Onshape add 8 yoke V-grooves, stator pole-side notches and 6 rotor lightening holes (polar arrays), export DXF (mm, splines not as polylines), import, evaluate, read the table, validate on `full`. Commit the DXF as `tests/topology/fixtures/onshape_8_6_edit.dxf` with a test that imports it cleanly.
2. Validation campaign for 0.5.0: tag, slow suite on CI, regenerate `docs/validation/*.json` and the report; add `"0.5.0"` to `VALIDATED_VERSIONS` only on verdict PASS.
