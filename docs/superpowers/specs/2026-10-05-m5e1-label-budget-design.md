# M5e1: EM-validated label, uncertainty budget, Js check, `iron_b_peak` — design

Status: owner-approved decisions (2026-10-05). Core spec: §2.3, §5.2 step 6, §7.3, §8.4, §8.5. Roadmap: `docs/m5-roadmap.md` M5e. M5e is split: **M5e1** (this spec, engine) and **M5e2** (library adds, validation report, CI slow suite on Linux, speed re-baseline; next session).

## Goal

One call tells whether a map of a design earns the label **"EM-validated"** (§8.5) and gives the §8.4 worst-case uncertainty of its key numbers. No label is awarded until M5e2 adds the engine version to the validated list.

## Owner decisions

1. **Convergence check (§8.5)** = a point check plus the existing FEM checks. Solve 4 key points on the `full` and on the `reference` mesh; ψ within 0.5 % (of that point's ψ) and torque within 1 % of peak torque. Also require `fem_checks` (held-out ψ and torque, band radius) to pass on the map. M5a worst full-vs-reference: ψ 0.25 %, torque 0.36 % of peak.
2. **Presets:** `full` and `reference` maps can earn the label; `screening` never.
3. **Validated engine version:** constant `VALIDATED_VERSIONS: tuple[str, ...] = ()` in `srmcore.maps.validation`; M5e2 adds the version once the validation report passes. Any other version: no label.
4. **Budget rows** (worst-case sum, relative): mesh, material, end effect, digitisation (definitions below).
5. **Material row** = Js ±2 % half-spread + grade allowance A 0 %, B 3 %, C 10 %. The ±2 % Js check (§5.2) is this row's first part.
6. **`iron_b_peak`** = area-weighted 99.9th percentile of iron |B|; warns above the last stacked B-H data point.
7. **Band noise in `full`:** accepted; the 1.7 % held-out limit covers it. §10 item closed.
8. **Point-check failure:** no label; the result names the failing point and the error. The adaptive `reference` preset stays deferred.
9. **API:** one entry `em_validate`; nothing stored in HDF5.
10. **Budget basis:** the end-winding-corrected key numbers (midpoint image factor 1.5); the 2D values are reported beside them.
11. **Js −2 %:** tried first; when the B-H data already exceed Js − 2 % (true for M19 and steel_1010: last-point J 2.006 T > 1.989 T and 2.073 T > 2.058 T), the half-spread is |value(+2 %) − value(nominal)|, and the result records that only +2 % was possible.
12. **Map warnings are informational.** No optimizer or search may use a map check's `warn` as a constraint; hard limits live in `srmapp` requirements.

## `iron_b_peak` spike (throwaway, 2026-10-05)

8/6 golden design, phase A at 20 A, NGSolve, iron |B| / Js at rotor angles 0, 5, 10, 15 and 20°:

| Mesh | nodes | max element | area p99.9 |
|---|---|---|---|
| screening | 42 935 | 1.196 – 1.472 | 0.782 – 1.077 |
| full | 81 984 | 1.260 – 1.531 | 0.778 – 1.077 |
| reference | 612 292 | 1.416 – 1.683 | 0.777 – 1.077 |

The element maximum grows with refinement (pole-corner singularity); p99.9 changes by at most 0.005. M19's last stacked data point is about 2.26 T (1.11 Js), so the golden's check returns to `pass`.

## Design

### 1. `b_peak` (`maps/point.py`)

`PointResult.b_peak` and `MapResult.b_peak` keep their names and become the area-weighted 99.9th percentile of |B| over stator and rotor iron elements: sort element |B|, cumulative element area, first value where the cumulative fraction reaches 0.999. Constant `B_PEAK_QUANTILE = 0.999`. Field comments and the dataset docstring are updated. The srmcore version goes to 0.3.0 (the cache key carries the version, so stored maps with the old definition become misses).

### 2. `iron_b_peak` check (`maps/checks.py`)

Value = max `b_peak` / B_last, limit 1.0, `warn`. B_last = the smaller of the stator and rotor laws' last stacked data point (`BHCurve.bn`). Detail text: "area p99.9 iron |B| / last stacked B-H point (beyond it the law is the Js tail)". `tests/maps/goldens_8_6.json` is regenerated (the status goes to `pass`).

### 3. Material schema (`materials/schema.py`)

`SoftMagneticMaterial.digitisation_error: float | None = Field(default=None, ge=0, lt=0.5)`: relative B error of a digitised curve (grade B). None means 0 in the budget. No existing JSON changes.

### 4. `maps/validation.py` (new)

```python
VALIDATED_VERSIONS: tuple[str, ...] = ()
LABEL = "EM-validated"
PSI_POINT_TOLERANCE = 0.005      # of the point's ψ
TORQUE_POINT_TOLERANCE = 0.01    # of peak torque
JS_STEP = 0.02
GRADE_ALLOWANCE = {"A": 0.0, "B": 0.03, "C": 0.10}
KEYS = ("la", "lu", "peak_torque", "psi_max")

@dataclass(frozen=True)
class BudgetRow:
    source: str                  # "mesh" | "material" | "end_effect" | "digitisation"
    rel: dict[str, float]        # key -> relative half-spread
    note: str

@dataclass(frozen=True)
class UncertaintyBudget:
    values_2d: dict[str, float]  # key numbers of the 2D map
    values: dict[str, float]     # with the end winding at image factor 1.5 (la, lu, psi_max change)
    rows: tuple[BudgetRow, ...]
    total: dict[str, float]      # worst-case sum of the rows, relative to `values`

@dataclass(frozen=True)
class EmValidation:
    label: str | None            # LABEL when every check passes
    checks: tuple[Check, ...]
    budget: UncertaintyBudget
    engine_version: str
    material_grades: dict[str, str]   # {"stator": "C", "rotor": "C"}

def em_validate(design, result, *, solver="ngsolve", workers=None) -> EmValidation
```

**Key points** (from the map and `key_numbers`): La at (θ_a, i_lo), Lu at (θ_u, i_lo), ψ_max at (θ_a, I_max), peak torque at the grid point (θ_pk, i_pk) of max |Arkkio torque|; i_lo = `LA_CURRENT_FRACTION` · I_max.

**Solves** (sequential, one solver, `solve_point` path): the 4 points on the `full` mesh, on the `reference` mesh, and on the map's own preset mesh with stator and rotor laws at Js · 1.02 and (when the data allow) Js · 0.98. The Js variants swap the iron laws in the built `Magnetostatic2D` (`dataclasses.replace(problem, laws=...)` with `law_for_material(material.model_copy(update={"saturation_polarisation": ...}))`); an `InputError` from the −2 % law means "data forbid it". Up to 16 solves; the reference mesh is built once.

**Checks** (each a `Check`; label only when all pass):

| name | pass when |
|---|---|
| `engine_version` | `version("srmcore")` in `VALIDATED_VERSIONS` |
| `preset` | map preset is `full` or `reference` |
| `no_filled_points` | map complete and `filled` has no True (no interpolated NONCONVERGED point) |
| `point_convergence_psi` | max over La, Lu, ψ_max points of \|ψ_full − ψ_ref\| / \|ψ_ref\| ≤ 0.5 % |
| `point_convergence_torque` | \|T_full − T_ref\| / peak torque ≤ 1 % at the peak point |
| `held_out_psi`, `held_out_torque`, `band_radius` | from `fem_checks(design, result)` |
| `material_grade` | stator and rotor materials carry a confidence grade (always true with the schema; recorded) |

A failing or non-converged key-point solve makes its check `fail` with the point named in the detail.

**Budget rows** (relative, per key):

- `mesh`: |full − reference| / |reference| at each key point (torque relative to peak torque).
- `material`: Js half-spread on the map's mesh, (|v₊ − v₋|)/2 / |v₀| or |v₊ − v₀| / |v₀| when −2 % is forbidden (note says which), plus `GRADE_ALLOWANCE` of the worse stator/rotor grade.
- `end_effect`: (L_end(k=2) − L_end(k=1))/2 · i / corrected value for La, Lu (i = i_lo) and ψ_max (i = I_max); 0 for torque. Note: "iron-end 3D fringing not modelled".
- `digitisation`: max of stator and rotor `digitisation_error` (0 when None), all keys.

`total` = sum of the rows per key. `values` = `values_2d` with La, Lu + L_end(1.5) and ψ_max + L_end(1.5) · I_max.

### 5. Exports

`srmcore.maps` exports `em_validate`, `EmValidation`, `UncertaintyBudget`, `BudgetRow`, `VALIDATED_VERSIONS`.

## Tests

Fast suite has about 40 s of headroom (545 tests, 9:21 of 10 min): fast tests are logic-only, each under a second.

- `b_peak` quantile helper: a hand-built set of elements (one huge |B| in a tiny element is ignored; uniform field returns it).
- `iron_b_peak` check on a fake `MapResult`: below and above B_last.
- Budget arithmetic and label rules on stubbed solves (monkeypatch the point solver): total = row sum; one failing check → label None; `VALIDATED_VERSIONS` empty → `engine_version` fails; screening → `preset` fails; a filled point → `no_filled_points` fails; −2 % forbidden → +2 %-only note.
- Schema: `digitisation_error` accepted, negative rejected.
- Slow: `em_validate` end to end on the 8/6 golden design at `full` (map from `build_map`); every check except `engine_version` passes, label None, budget totals finite and positive; goldens regenerated.

## Docs

Spec §10: close the band-noise and `iron_b_peak` [M5a→M5] items; §11 entry for these decisions; CLAUDE.md (map products list, `b_peak` definition, the informational-warnings convention); `docs/m5-roadmap.md` M5e split; a handoff for M5e2; the project doc.

## Not in M5e1

Library adds, validation report, `VALIDATED_VERSIONS` entry, CI slow suite on Linux, speed re-baseline (all M5e2). Adaptive `reference` preset (deferred until a design fails the point check). Storing the validation in HDF5.
