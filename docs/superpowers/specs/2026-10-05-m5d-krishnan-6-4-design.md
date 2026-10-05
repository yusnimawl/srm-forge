# M5d: measured Krishnan 6/4 and the end-winding hook (design)

Goal: compare srmcore with a measured SRM, reporting error ± uncertainty before and after an end-effect correction (core spec §2.3, §8.2 suite 5, §9 M5 row). Add the analytic end-winding inductance hook (core spec §7.1) and check it on TEAM 24, which is not used for calibration.

## Source

The 6/4 data in Krishnan, *Switched Reluctance Motor Drives* (2001), Table 2.3 come from P. N. Materu, *Design and steady-state analysis of the switched reluctance motor drive*, PhD dissertation, Virginia Tech, July 1989 (chair R. Krishnan), Table 1 p. 41 and Appendix A pp. 287–288 ([VTechWorks](https://vtechworks.lib.vt.edu/server/api/core/bitstreams/42cbb685-1d45-43ad-b5c4-ff568e609f1c/content)); also Materu & Krishnan, IEEE IAS Annual Meeting 1990 ([IEEE Xplore 152189](https://ieeexplore.ieee.org/document/152189/)). Table 1 was checked against the page image; it equals the book's Table 2.3.

Measured (Table 1): La 879 / 155 / 89 mH, Lu 35.5 / 40.7 / 35.6 mH, T_avg 0.90 / 20.3 / 41.6 N·m at 1 / 10 / 20 A. Materu's 2D FEA: La 843 / 133 / 75.5 mH, Lu 25.8 mH, T_avg 0.80 / 18.5 / 37.8 N·m.

Facts from the dissertation used below:
- Inductance was measured by voltage integration (ch. 8) at 5° steps and 0–20 A; Table 1 lists 3 currents. The measured T_avg is "torque computed using measured flux linkages" (p. 49), not a torque-transducer reading, so it is not independent of the measured L.
- The dissertation attributes the Lu error to end effects and cites a 3D-vs-2D FEA study (Seward, Forghani, Arumugam, Lowther, Lindsay, SATECH'87): end leakage ≈ 7.5 % of aligned and 35 % of unaligned inductance. Used as a reference line, not as a correction.

Appendix A vs the book:

| Field | Dissertation | Book |
|---|---|---|
| Bore diameter | 122.0 mm | 102.06 mm |
| Stator back iron | 10.15 mm | 10.515 mm |
| Shaft diameter | 28.56 mm | — |
| Rotor pole height | 27.25 mm | — |
| Core material | "E140 steel" | M19 |

Core length 60.37 mm, OD 190 mm, gap 0.25 mm, arcs 24°/36°, 536 turns/phase, AWG 19, rated 10 A, 300 V, 1800 rpm agree.

## Spike results (throwaway, `screening`, NGSolve, coil clearance 0.5 mm, fill 0.4)

| Variant | La 1 / 10 / 20 A (mH) | Lu 10 A (mH) | T_avg 1 / 10 / 20 A (N·m) |
|---|---|---|---|
| Bore 102.06, M19 | 848 / 131 / 69.7 | 37.4 | 0.80 / 17.5 / 32.7 |
| Bore 122.0, M19 | 907 / 131 / 70.0 | 33.3 | 0.93 / 18.2 / 34.7 |
| Bore 102.06, steel_1010 | 676 / 134 / 72.3 | 37.0 | 0.63 / 17.6 / 33.7 |

- Bore 102.06 reproduces Materu's 2D FEA at 1 A (La within 0.6 %, T_avg equal); 122.0 misses by 8 % and 16 %.
- Our 2D Lu (33–45 mH) is far above Materu's FEA (25.8 mH) and near the measured value.
- Coil placement drives Lu: moving the coil from the bore to the yoke (clearance 0.5 → 18 mm) raises Lu 37 → 45 mH (bore 102.06); La moves < 1 %.
- Material moves La at 1 A by 20 % and La at 20 A by 4 %; Lu not at all.
- Measured La at 20 A (89 mH) means φ = 3.3 mWb: ≈ 2.6 T over the stator pole (21.4 × 60.4 mm) or ≈ 2.6 T in the 10.5 mm yoke halves, above any steel's Js. The deep-saturation deficit cannot come from the 2D lamination model; it is end flux or the measurement.

## Owner decisions (2026-10-05)

1. **Geometry: book bore 102.06 mm and back iron 10.515 mm; shaft 28.56 mm and rotor pole height 27.25 mm from the dissertation** (rotor yoke = 50.78 − 14.28 − 27.25 = 9.25 mm). The dissertation's bore 122.0 / back iron 10.15 mm is a sensitivity row in the uncertainty budget. Fillets and tapers 0. Built inside `waive_rules("self_starting")` (βs 24° < 30°).
2. **Coil: packed against the yoke, bundle packing 0.5.** Copper per coil side 268 × 0.653 mm² (AWG 19 bare) = 175 mm²; coil-side area 350 mm²; `coil_inner_clearance` solved so the topology coil side has that area. Liner 0.3 mm. Packing 0.35–0.65 is an uncertainty row. `fill_factor` 0.5 (it does not change ψ or T).
3. **Material: M19 library curve (grade C)** for stator and rotor; "E140" is unidentified. Material row: the M19 vs steel_1010 spread per point, labelled a crude bound. No new library curve; new grades stay a JSON file each.
4. **End-winding hook: analytic end-turn inductance, no calibration.** Not an axial-length factor (the right factor depends on position) and not a correction fitted to the 6/4 (circular). The 3D fringing of the iron ends stays uncorrected and is reported as the residual.
5. **Data: Table 1 values only** (typed, no digitisation error). The figure curves are not digitised.

## Design

### 1. End-turn formula (`srmcore/post/end_winding.py`)

`end_turn_inductance(turns, span, build, depth, image_factor=1.0) -> float` (H per coil), plain numbers in SI.

- The two end overhangs of one pole coil together form one closed loop around the pole end. They are modelled as a circular loop of mean diameter `span` (the coil's mean span across the pole), with conductor bundle of rectangular section `build × depth`.
- L = image_factor · μ0 · N² · R · (ln(8R / g) − 2), R = span / 2, g = 0.2235 · (build + depth) (geometric mean distance of a rectangle). Thin circular loop (Rosa / Grover, *Inductance Calculations*, 1946); the implementer confirms the formula and the GMD constant from a source and cites it in the docstring.
- `image_factor` 1 is the coil in free air (no iron image; lower bound); 2 is a coil against an infinitely permeable end face (upper bound). Default 1. The 1-to-2 spread is the "end-winding model" uncertainty row.
- Raises `ValueError` on non-positive inputs or g ≥ R.

### 2. Machine adapter and map correction (`srmcore/maps/end_winding.py`)

- `coil_geometry(machine: RadialSRMParams) -> CoilGeometry` (frozen dataclass: `area`, `depth`, `build`, `span`, m and m²): from `topology.build_outline` coil side A1+; area by shoelace over the boundary with arcs sampled finely; depth = r_out − r_in; build = area / depth; span = stator pole chord width at mid-depth + 2 · liner + build.
- `end_winding_inductance(machine, image_factor=1.0) -> float`: H per phase = `end_turn_inductance(turns_per_pole, ...)` × poles per phase (series; mutual coupling between a phase's coils neglected, they sit on opposite sides).
- `with_end_winding(result: MapResult, l_end: float) -> MapResult`: ψ[..., excited] += l_end · i; energy and coenergy += ½ · l_end · i²; l_inc[..., excited] += l_end where not NaN. Torque unchanged. Pure, returns a new result.
- The 2D FEM map, its cache key, goldens and FEMM fixtures are unchanged: the correction is never applied inside `build_map`.

### 3. 6/4 machine (`tests/krishnan_6_4.py`)

- `machine(bore="book" | "dissertation", packing=0.5) -> RadialSRMParams` per decisions 1–2; `design(..., material="M19", preset="reference") -> Design`. The clearance is found by bisection on `coil_geometry(...).area`.
- `MEASURED`, `MATERU_FEA` (Table 1), `SEWARD_END_LEAKAGE = {"aligned": 0.075, "unaligned": 0.35}`, `ASSUMED` (field → reason).
- `table(design, solver) -> dict`: La, Lu (secant ψ/i at 0 and π/4) and T_avg = m·Nr · (W′_aligned − W′_unaligned) / 2π (Krishnan's stroke-averaged definition; m·Nr = 12) at 1, 10, 20 A, each solved with `solve_point` from A = 0.
- `budget(...)`: per quantity and current, the half-spread of each row: mesh (`full` vs `reference`), material (M19 vs steel_1010), geometry (book vs dissertation bore), coil packing (0.35 vs 0.65), end-winding model (image factor 1 vs 2, after-correction column only), measurement (Lu ±7 %: half the 35.5–40.7 spread; La and T: not stated, recorded as unknown). Rows combine as worst case (sum of absolute values), per core spec §8.6.

### 4. Report (`examples/krishnan_6_4_check.py` → `docs/m5d-krishnan-results.md`)

`PYTHONPATH=tests .venv\Scripts\python examples\krishnan_6_4_check.py` prints and writes the tables: for La, Lu, T_avg at 1/10/20 A: measured, Materu FEA, srmcore 2D, srmcore 2D + end winding, error % before and after, uncertainty ±% before and after, and the Seward 3D reference line. The doc explains: measured T_avg is derived from measured ψ; the 20 A La saturation argument; the residual end flux the hook does not model.

### 5. TEAM 24 independent check

`tests/team24_fixture.py` gains the rig's coil geometry for `end_turn_inductance` (350 turns, coil sides 24 × 17 mm, 34 mm hole). Static torque and rotor-pole flux at steady state: the hook changes ψ only (torque is unchanged, flux in the rotor pole is unchanged); what changes is the steady-state ψ and the current-rise integration (dψ/dt = V − R·i). `examples/team24_check.py` reports the current rise before and after; `docs/m5b-team24-results.md` gets the comparison. TEAM 24 is never used to tune the hook.

### 6. Tests

- Fast: `tests/post/test_end_winding.py`: the formula against a hand-computed circular-loop value; `image_factor` scaling; `ValueError` cases. `tests/maps/test_with_end_winding.py`: on a small synthetic `MapResult` (no FEM), ψ, energies and L_inc shift exactly and torque does not. `coil_geometry` on `make_8_6`: area equals the coil region area of the static mesh within 0.5 % (reuse an existing session fixture if one exists; otherwise mark slow).
- Slow: `tests/validation/test_krishnan_6_4.py` pins the 2D and corrected tables (rtol 1e-3) and the signs (after correction Lu error moves toward 0 or flips sign; La within the stated uncertainty band at 1 A). TEAM 24 slow test pins the corrected steady-state ψ.
- Import rules: `post/end_winding.py` imports only numpy/math; `maps/end_winding.py` may import topology.

### 7. Docs

Spec §11 entry (decisions, result), §9 M5 row, §10 item closed, `docs/reference-machines.md` 6/4 row (source, Appendix A, bore conflict), `docs/m5-roadmap.md` M5d marked done, `CLAUDE.md` current state, the living project doc.

## Out of scope

3D fringing factor (core spec §7.1: only after calibration against measured data; one sparse machine is not enough); digitising the dissertation's figures; an E140 library curve.
