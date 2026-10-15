# R2 — DXF round trip — Design Spec

Status: approved in chat 2026-10-15 (owner). Parent: `2026-10-12-roadmap-r1-r10-design.md` §3 R2.

## 1. Goal

The owner exports a case's laminations as DXF, edits the iron in CAD (Onshape is the reference tool), imports the file, and gets a map, the usual products and a before/after comparison from the same engine. Done when this works end to end on the 8/6 (§9).

## 2. Decisions (owner, 2026-10-15)

- Only the iron is imported. Coils, the winding, the band radii and the end-winding geometry stay parametric.
- Edits must repeat every pole pitch: stator edits every 360°/Ns, rotor edits every 360°/Nr. Anything else is refused with the rule, the offending feature and an example fix. Mirror symmetry is not required. Per-phase maps for non-repeating edits are out of scope (§10).
- Regions come from geometry, not DXF layers (Onshape has no layers). Layers are written on export for reading only.
- The round trip runs in the web app: Export DXF and Import DXF on a case, a new draft case linked to its parent, a before/after table.
- The imported shape enters the pipeline as an extended `RadialOutline` (approach 1). Boolean diffs against the parametric shape were rejected (near-coincident edges give slivers); Gmsh cannot read DXF.

## 3. Data model

- `srmcore.model`: new frozen model `ImportedIron` with closed loops of `Line` and `Arc` in metres:
  - `stator_outer`: the stator outside contour;
  - `stator_bore`: the stator bore contour with its poles;
  - `stator_holes`: holes in the stator lamination;
  - `rotor_outer`: the rotor outside contour with its poles;
  - `rotor_bore`: the rotor inside contour (the shaft hole);
  - `rotor_holes`: holes in the rotor lamination.
- `Design.iron: ImportedIron | None = None`. When `iron` is `None` the design JSON is byte-identical to today's (the field is omitted), so every existing design hash, cached map and golden stays valid. `Design.schema_version` stays 1; an older srmcore refuses a design with `iron` through `extra="forbid"`, which is correct.
- Loops are canonical before they are stored: points rounded to 0.1 µm, each loop starting at its point of smallest (angle, radius) and running counter-clockwise, loops sorted. Re-importing the same shape gives the same `design_hash` and reuses the cached map.
- Splines are flattened to lines with a chord error of at most 1 µm. Lines and arcs are kept as they are.
- On a design with `iron`, `RadialSRMParams` still defines the coils, the band radii, the winding, the end-winding geometry and the reference values the import checks compare against.

## 4. Pipeline

1. `topology/radial.py` `build_outline` builds the outline as now. When `design.iron` is set, its contours replace the iron contours. Coil sides, band radii and refinement features stay parametric.
2. `RadialOutline` gains optional fields: a free stator outer contour (in place of the circle), stator holes, a free rotor bore contour (in place of the shaft circle) and rotor holes. A parametric design leaves them empty and builds exactly as before.
3. `geometry/build.py` uses the free contours when present and cuts the holes. Region names and kinds are unchanged; holes are air.
4. The importer adds refinement points on every imported edge shorter than the local mesh size, so the existing size field refines small features. The quality gate is unchanged; a failure names the feature.
5. Meshing, the moving band, solves, maps, map products and `em_validate` are unchanged.
6. `srmapp.sizing.estimates.active_mass` uses the imported iron area (holes subtracted) when `iron` is set: area × stack length × density × stacking factor from the material data. Copper is unchanged.

New modules:

- `topology/dxf_io.py`: DXF read and write through ezdxf (new dependency, MIT licence). It is the only module that imports ezdxf.
- `topology/imported.py`: loops to `ImportedIron`, and the import checks (§5).

`topology` still imports only `model`; the import-rule table does not change.

## 5. Import checks

Every check runs and every problem is reported together: rule, location in mm in the DXF's own coordinates, and how to fix it. Any failure refuses the import and nothing is created.

1. **File.** Units from `$INSUNITS`: mm, or none (read as mm); inch and m are converted; any other unit is refused. Every entity must sit at the same z (any value); otherwise the file is refused, naming one entity at another z. Supported: LINE, ARC, CIRCLE, LWPOLYLINE and POLYLINE (bulges become arcs), SPLINE (flattened), INSERT (exploded). TEXT, MTEXT, DIMENSION, HATCH and POINT are ignored. Any other entity is refused by type.
2. **Closed loops.** Endpoints join within 1 µm. Open ends, duplicate or overlapping edges and self-intersections are each reported with coordinates.
3. **Centre and rotor angle.** The machine centre is at the origin, and the rotor sits at the exported angle (a rotor pole on phase A, angle 0). A shifted or rotated drawing is refused with the offset or angle found.
4. **Bodies.** Loops nest into exactly one stator lamination and one rotor lamination, each one connected piece, plus holes. Loops that match a parametric coil side within 1 µm are dropped first (exported coils coming back). Any other loop is refused as stray.
5. **Air gap.** No stator iron at a radius below the bore radius, no rotor iron above the rotor radius, and the band annulus is free. Pole faces may be notched outward from the gap, never into it.
6. **Coils.** No iron inside a parametric coil region. Iron removed next to a coil becomes slot air.
7. **Repeat.** The stator is unchanged under a rotation of 360°/Ns and the rotor under 360°/Nr, within 1 µm. Example message: "Stator edit near (61.2, 4.0) mm repeats 2 times; it must repeat every 45° (8 times on this 8/6 stator). Draw it once and polar-array it 8× around the centre."
8. **Web width.** The narrowest iron anywhere (hole to edge, groove to bore, narrow necks) is at least max(1 mm, 2 × lamination thickness), the existing rule. The narrowest place is reported.

Warning (not a refusal): iron area changed by more than 10 % from the parent, a hint of the wrong file or wrong units.

## 6. Export

- `Export DXF` on any case: R2010 DXF, `$INSUNITS` = mm, rotor at angle 0, arcs as arcs, the stator outside as a CIRCLE when parametric.
- Layers `STATOR`, `ROTOR`, `COILS`. Coil outlines are written for reference; §5.4 drops them on import.
- A case with `iron` exports its imported contours, so export, edit and import can repeat.

## 7. Web

- Routes: `GET /api/cases/{id}/dxf` (export), `POST /api/cases/{id}/dxf` (import; 422 with the problem list from §5, or the new case).
- Import creates a stale draft case: the parent's inputs plus `iron`, label "DXF edit of <parent label>", linked to the parent.
- Store schema v3: a `parent_case_id` column, migrated automatically from v2 (and v1 through v2).
- Setup files carry `iron` inside the design; the `srm-setup` schema version goes up by one and older files still import.
- `/api/geometry` draws the imported contours.
- Locked geometry: on a case with `iron`, the geometry parameters are read-only in the edit form; winding, limits and requirements stay editable. To change parameters, edit the parametric parent and import again.
- Before/after on a case with `iron` whose parent is evaluated: a table of La, Lu, peak torque, ψ_max, stator iron mass, rotor iron mass and total mass, each as before, after, Δ and Δ %. Both cases are shown in the graphs by default, so the existing overlays give ψ(θ) and torque. If the parent is not evaluated, the table says so and offers to evaluate it.
- The import dialog lists every problem from a 422.
- A case with `iron` can be validated (`full` preset) like any other.

## 8. Versions

- srmcore 0.5.0, srmapp and srmweb 0.5.0, `web/` 0.5.0.
- `"0.5.0"` joins `VALIDATED_VERSIONS` only after the slow suite passes on CI for the tag and the validation report verdict is PASS, as for 0.4.0. Until then, results are labelled Unvalidated.
- Changing the version changes map provenance, so cached maps are rebuilt once.

## 9. Tests and done

- **No-edit round trip:** export the 8/6, import it unchanged; the design hash, the outline and a solved point (ψ, torque) equal the parametric ones.
- **Refusals:** one DXF per check in §5, generated with ezdxf inside the test (open loop, wrong units, non-flat z, rotated rotor, iron in the gap, iron in a coil, non-repeating edit, thin web, stray loop), each asserting the rule and location reported.
- **Physics sanity:** rotor holes lower the mass by area × stack × density and change La only a little; a stator yoke groove lowers ψ at I_max a little.
- **Onshape fixture:** the file the owner exports in the done step is committed and read by a test.
- **Web:** route tests (export, import, 422 list, parent link, v2→v3 migration, setup round trip), vitest for the import dialog and the before/after table, and a visual check on `srmweb-smoke`.
- **Done when:** on the 8/6, export; in Onshape add 8 yoke V-grooves, stator pole-side notches and 6 rotor lightening holes; import; evaluate; the before/after table shows; and validate on the `full` preset passes (2D-verified).

## 11. Rulings from planning (2026-10-15)

These amend the sections above where they differ.

1. `iron` lives on `RadialSRMParams` (`Design.machine.iron`), not on `Design`. Every stage takes the machine parameters (`build_outline`, stage 1 mass, the outline SVG, setup files), so the imported iron reaches them without new plumbing. It is still omitted from JSON when None, and the design hash covers it.
2. Stator outside edits only cut inward: the outer contour stays within the stator OD. A = 0 stays on the OD circle, and groove space is air (region `stator_hole_air`). The rotor bore may only open outward from the shaft circle; the shaft stays a circle and the pockets are air (`rotor_hole_air`). Stator holes and rotor holes are in those regions too. Before and after then share the same boundary condition.
3. After rounding, vertices within 1 µm of the bore, rotor, stator-OD or shaft circle are projected onto it, and arc centres within 1 µm of the origin are moved to it. Without this, a CAD round trip leaves sub-micron rings next to those circles and the mesh gets slivers.
4. No store schema bump: `cases.parent_case_id` already exists; the new origin is `dxf`. No setup-file version bump: the setup's `geometry.machine` carries `iron`, and an older tool refuses it through `extra="forbid"`.
5. The iron checks also run in every case check (raw inputs and setup files are trust boundaries) and in `build_outline`, which raises `InputError` on a failed check.
6. §9 no-edit test: an imported design has `iron` set, so its hash differs from the parametric one. The test asserts the outline matches and a solved point agrees (ψ within 1e-5 relative, torque within 1e-4 of peak); a second import of the re-exported file gives the same hash.
7. Iron closer than half the slot-liner thickness to a coil is refused (rule `coil_overlap`).
8. Imported edges that differ from the parametric outline, and all holes, get the refinement tag `iron_detail` at size max(min web width / 2, air-gap size).
9. Before/after masses and key numbers come from a server route, `GET /api/cases/{id}/compare`.
10. The bench gets ezdxf in its lock and new 0.5.0 reference points and goldens.

## 10. Out of scope

- Per-phase maps for edits that do not repeat every pole pitch.
- Editing coils.
- Searching or optimising over DXF shapes.
