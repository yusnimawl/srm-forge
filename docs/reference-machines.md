# Reference machines for validation (M1 audit)

Criteria: (a) full geometry, (b) B-H data of the lamination, (c) MEASURED ψ(θ,i) and/or static T(θ,i).

Library searched: `D:\y\srm` (read-only, ~60 PDFs). Exact filenames confirmed via directory listing.

**Escalation:** none of the machines selected below satisfies (a)+(b)+(c) together, and two of them fail the
validator's `self_starting` rule as published — see the M5 open item in spec §10
(`docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`) for the full list and the owner decisions needed.

| Candidate | Source file | Pages / figures | Topology | (a) geometry | (b) B-H | (c) measured ψ / T | Qualifies | Notes |
|---|---|---|---|---|---|---|---|---|
| TEAM Problem 24 | ngsolve.github.io TEAM-24 page + original TEAM report (Allen & Rodger, Univ. of Bath, fetched from `compumag.org/.../problem24.pdf`, linked from the NGSolve page) | Fig. 1–2 (geometry), Fig. 3 & Table I (B-H), Figs. 5–9 & Tables II–VI (measured step-voltage/current/torque/flux/B) | Single-pole-pair SRM-like rig (locked rotor at 22°, not a conventional multi-pole rotating SRM) | **Yes** — full dimensions in Fig. 1 (stator Ø209.0 mm, rotor Ø102.1 mm outer / Ø50.8 mm shaft, rotor pole height 12.7 mm, axial length 25.4 mm) and Fig. 2 (two 350-turn coils, 3.09 Ω total, wire Ø1 mm, coil section 24×17 mm²) | **Yes** — Table I / Fig. 3: measured EN9 medium-carbon-steel initial magnetization curve (Magnet-Physik Remagraph RE3 BH tester up to ~2 T, extended to 2.5 T by Lucas A.V.S.D.), 21 tabulated (H, B) points | **Yes** — Figs. 5–9 / Tables II–VI: measured step voltage (23.1 V), coil current, torque (piezoelectric force link, radius 0.268 m), rotor-pole search-coil flux, and Hall-probe air-gap flux density, all vs. time, for a single locked-rotor step-voltage test | **Yes, for its own scope** | Not a standard multi-pole rotating SRM — no `RadialSRMParams` mapping is produced for it (see Decision). Use directly per spec §2.3 (magnetostatic/current-rise scope, TEAM24 test suite 5). |
| Krishnan 8/6 design example | *Switched Reluctance Motor Drives* (Krishnan & Irwin, CRC 2001), Ch. 2 §2.3.4 "Results and Comparison" (file `0838_pdf_c02.pdf`, "second machine with 8/6 poles" table) and a *separate, unrelated* 8/6 prototype in Ch. 3 §3.9.5 "Selection of Pole Base" (file `0838_pdf_c03.pdf`, verified via `pdftotext`) | Ch.2 table immediately after Table 2.3; Ch.3 table before Fig. 3.23 | 8/6, 4-phase | **Yes** (Ch.2 table: 8 stator/6 rotor poles, 5 hp, stator pole arc 18°, rotor pole arc 22°, air gap 0.5 mm, OD 190 mm, bore 100.6 mm, stack 200 mm, shaft 28 mm, 1500 rpm, stator back-iron 12 mm, stator pole height 32.7 mm, rotor pole height 19.8 mm, turns/phase 154 [= 77 turns/pole; see mapping table], conductor 1.588 mm², rated 13 A) | **Not found** — lamination named "M43" (Ch.2), but neither chapter reproduces a B-H table/plot for it | **No — FEM only.** Ch.2 gives "Finite Element Analysis (mH) vs. Analytical (mH)" for aligned/unaligned inductance (65.41/66.79 and 11.35/11.38 mH, immediately following the M43 dimensions table — this comparison *is* for the M43 machine, confirmed by `pdftotext` line adjacency) — no bench measurement. Ch.3 §3.9.5's pole-base-shaping study (Fig. 3.23) is a **different, M19-cored** 8/6 prototype (0.3 mm gap, 100 mm bore, 144 turns/phase, 0.7 fill factor, 12 A/500 V p.u. basis — none of these match the Ch.2/M43 machine) and is also FEM-only. | **No** (fails b, c) | Used per spec §2.3/§8.2 as the **FEMM-comparison** reference only (that role does not require measured data); the mapped `RadialSRMParams` values below are the Ch.2/M43 machine only — the Ch.3/M19 machine is a distinct, unmapped prototype, cited here only to show the material-grade landscape in this book. See the companion **Krishnan 6/4 prototype** below, found in the same chapter, which does have genuine measured data. |
| Krishnan 6/4 prototype (supplementary — not in brief's original list, added because it directly serves the "measured SRM reference" decision) | Same book, Ch. 2, Table 2.3 "Comparison of Inductance by Various Methods" and preceding text (file `0838_pdf_c02.pdf`) | Table 2.3 and the dimensions table immediately before it | 6/4, 3-phase | **Mostly yes** (stator OD 19 cm, core length 6.037 cm, air gap 0.025 cm, back-iron thickness 1.0515 cm [table does not say stator vs. rotor], stator pole arc 0.418 rad, rotor pole arc 0.628 rad, turns/phase 536 [= 268 turns/pole; see mapping table], wire AWG #19, core M19 steel); shaft diameter and speed rating **not found**. **Label ambiguity resolved:** the source's dimensions table literally labels one row "Rotor diameter (bore) 10.206 cm" (confirmed verbatim via `pdftotext`), which read alone could mean either "the rotor's own OD" or "the bore, i.e., the stator inner diameter the rotor fits into." Since a separate 0.025 cm air gap is also given, "10.206 cm" must be the **bore/stator-inner diameter**, not the rotor's own OD — the rotor's actual OD is 10.206 cm − 2×0.025 cm = 10.156 cm, computed below. | **Not found** — "M19 steel" named, no curve reproduced | **Yes** — Table 2.3: measured unaligned inductance, aligned inductance, and stroke-averaged electromagnetic torque (Krishnan's Table 2.3 averages torque over a switching stroke, not an instantaneous static T(θ) value) at three currents (1 A, 10 A, 20 A: e.g. 35.5/879/0.90, 40.7/155/20.30, 35.6/89/41.60 — measured columns), alongside analytical and FEM columns for comparison | **No** (fails b only) | Nearest 8/6-class machine in the library with real bench data (sparse — only 2 rotor positions × 3 currents, not a full ψ(θ,i) map). Selected as the primary **measured-data reference**. |
| Mak MASc thesis machine | `Mak_Christopher_See-Hon_2020aug_MASc (1).pdf` — "18/12 Switched Reluctance Motor Design for a Mild-Hybrid Electric Powertrain Application" (McMaster, 2020) | Table 5.7 p.77 (finalized geometry); Fig. 3.6 p.34 (generic illustrative curve only) | 18/12, 3-phase (belt-alternator-starter traction class) | **Partial** — pole counts, phases, OD 170 mm, rotor OD 110.6 mm, air gap 0.5 mm, stack 62.5 mm, pole arcs 11°/11°, stator/rotor taper 0.8°/2°, pole-tip/root fillets (1/0 mm stator, 1/0.5 mm rotor). **Not found**: yoke thicknesses (not a clean concept — spoked rotor), fill factor, slot liner thickness, coil inner clearance, lamination thickness, max speed (only a ~1500–1667 rpm idle target), lamination material grade. Shaft found separately (4340 steel, non-laminated). | **Not found** — Fig. 3.6 is a generic textbook flux-linkage illustration borrowed from a different thesis (Jiang's), not this machine's own material data; no steel grade is ever named for the core | **No — FEM only.** Entirely a JMAG/Matlab design study; Ch.7 "Future Works" explicitly lists prototype build/test as unfinished. No bench data anywhere. | **No** | 18/12 is traction-class, not 8/6-class. Excluded from all three selection slots. |
| Azer PhD thesis machine | `Azer_Peter_202006_PhD.pdf` — "Mutually Coupled Switched Reluctance Machines: Fundamentals, Modeling, and Control" (McMaster, 2020) | Table 5.1 p.55 (geometry); Figs. 5.18–5.23 pp.85–89 (measured current) & Figs. 7.15–7.19 pp.147–154 (current + oscilloscope "torque" trace) | 12/8, 3-phase (small 2 kW lab prototype, originally a conventional SRM rewound for mutually-coupled operation — not traction-scale despite the 12/8 count) | **Partial** — pole counts, phases, stator OD 136 mm, rotor OD 83 mm, air gap 0.3 mm, stack 70 mm, turns/phase 28 (ambiguous shaft: 38 mm EM cutout vs. 70 mm mechanical cutout in the table). **Not found**: pole arcs, tapers, yoke thicknesses, fillets, fill factor, slot liner, coil clearance, lamination thickness, lamination material grade (never named anywhere in the thesis) | **Not found** | **Corrected — overstated in an earlier draft of this audit.** Ch.5 §5.4 (Figs. 5.18–5.23, Table 5.5 p.85): genuinely **measured phase current** on a dynamometer-loaded bench at stated (id,iq) setpoints, 500–1500 rpm ("the phase current waveforms are measured and recorded by an oscilloscope" — no torque is claimed or shown in this section at all, confirmed by `pdftotext`). Ch.7 §7.5 (Figs. 7.15–7.19, Tables 7.1–7.2 pp.149,155): the whole thesis's control/validation method (Ch.5–7) is built on an FEA-derived torque look-up table Te = f(id, iq, θ) run on the DSP; no torque transducer, torque cell, or torquemeter is mentioned anywhere in the document (confirmed by full-text search). The Ch.7 oscilloscope "torque" traces are therefore best read as the **DSP's real-time LUT-based torque estimate driven by the measured currents**, not an independent physical torque measurement — an earlier draft of this audit called this "measured torque," which overstates it. No static locked-rotor T(θ) or ψ(θ,i) sweep either way. | **No** (fails a, b, and (c) for torque specifically — current is genuinely measured, torque is model-estimated from current) | Has real measured current data (and a model-based torque estimate) but geometry is too incomplete to build a mesh from; kept as a secondary cross-check candidate only, not selected as the primary measured reference. |
| 24/16 traction SRM | `THREE-PHASE 24 16 SWITCHED RELUCTANCE MACHINE FOR HYBRID ELECTRIC POWERTRAINS DESIGN AND OPTIMIZATION.pdf` — James Weisheng Jiang PhD thesis (McMaster, Dec. 2015, supervisor Ali Emadi) | Table 4.1 p.73, Table 4.2 p.80 (initial sizing), Tables 6.2–6.4 pp.138–146 (optimized/selected geometry), §4.3 p.78 (lamination) | 24/16, 3-phase (traction, sized to match the 2010 Prius MG2 envelope) | **Partial, substantial but incomplete** — stator OD 264 mm, air gap 0.5 mm, shaft 52 mm, stator pole arc 7.0°, rotor pole arc 7.2° (Case C3), stator pole taper 6° (Case B7), stator yoke 15 mm (Case B7), stator pole-shoe fillet 1 mm (Case D3), turns/pole 15 (10 strands, 20 AWG), fill factor ≈0.54, lamination 0.1 mm. **Not found / not finalized**: stack length (only derivable ≈92 mm active from 108 mm total minus 16 mm end-turn allowance), rotor pole taper (only an initial 3–8° range), rotor yoke thickness, rotor fillet radius, slot liner thickness, coil inner clearance, shaft/coil material grade. (Rotor OD is **not** a gap: 183 mm, derived from the stated 92 mm stator bore radius minus the 0.5 mm air gap — see the Decision section and parameter-mapping table below.) | **Not found** — lamination named "10JNEX900" (JFE Steel "Super Core"), saturation flux density 1.91 T stated, but no B-H curve/table reproduced (cites a manufacturer datasheet by reference only) | **No — FEM only for the 24/16 machine itself.** Entire thesis is JMAG FEA; no 24/16 prototype was built. (A *different*, smaller 12/8 SRM elsewhere in the same thesis, Ch.5 Fig. 5.5 p.96 and Figs. 5.22–5.24 pp.120–123, WAS bench-validated for flux linkage vs. rotor position and current waveforms — but that 12/8 machine's own geometry is not given, so it can't substitute.) | **No** (fails b, c; a is incomplete) | Best available 24/16 candidate in the library. Companion journal paper (Jiang, Bilgin, Emadi, IEEE Trans. Transportation Electrification 2017 — describing the same machine) is cited but not present in this library; it might close some of the (a) gaps. |
| 24/16 NVH machine | `Prediction of acoustic noise and vibration of a 24 16 traction switched reluctance machine.pdf` — Liang, Jiang, Callegaro, Bilgin, Dong, Reeves, Emadi, *IET Electrical Systems in Transportation* 10(1), 2020 | Table 1 p.36 (geometry subset), Table 2 p.39 (structural FEA properties, not magnetic), Figs. 21–22 p.42 (hammer-test measurement) | 24/16, 3-phase — **confirmed same physical prototype** as the "24/16 traction SRM" row above (paper's ref. [1] is Jiang/Bilgin/Emadi 2017; Table 1 is explicitly captioned as reproducing that paper's numbers; same McMaster MARC research group) | **Mostly not found** — only reproduces a headline subset from the companion paper: stator OD 264 mm, air gap 0.5 mm, stack (axial active length) 108 mm, fill factor 0.54, lamination 0.1 mm, max speed 13,500 rpm. All pole/yoke/fillet/turns/clearance fields not found here (not this paper's subject). | **Not found** — no B-H curve at all; Table 2 gives only *structural* material properties (density, Young's modulus, Poisson's ratio) for stator core, coils, and housing, used for modal/acoustic FEA, not magnetic FEA | **No, for ψ/T — only structural.** Sole physical measurement is a hammer (impact-modal) test on the dyno-mounted prototype (Fig. 21, p.42): measured natural frequencies 1735 Hz and 4852 Hz (Fig. 22b) vs. simulated 1782/4784 Hz (Table 3, p.41). All sound-pressure-level and vibration-under-operation results (Figs. 14–20) are simulated ("virtual microphones"/ACTRAN), not measured. No measured ψ(θ,i) or T(θ,i) anywhere. | **No** | Data-quality note: this paper names the lamination "NO10" (Cogent Power Inc.) while the companion 2015/2017 thesis names it "10JNEX900" (JFE Steel) for the same physical machine — an unresolved inconsistency between the two sources about the same prototype's core material. |

## Decision

- **8/6 (or nearest) FEMM + measured reference:** Two machines from the same book, since no single 8/6-class source in the library has both.
  - **FEMM-comparison reference:** Krishnan 8/6 design example (5 hp, 190 mm OD, **M43** core; Krishnan & Irwin 2001, Ch. 2 §2.3.4). Full geometry given; the book's own FEM-vs-analytical inductance comparison (no bench data) is for this same M43 machine (confirmed with `pdftotext`: the comparison numbers follow immediately after the M43 dimensions table in the source) and is exactly what spec §8.2 suite 4 needs. (The book has a *second*, unrelated 8/6 FEM study, Ch. 3 §3.9.5, that uses **M19** steel instead — a different prototype with different dimensions, not mapped here; see the audit table's Notes column.)
  - **Measured-data reference (nearest topology):** Krishnan 6/4 prototype, same book (Table 2.3). Genuinely measured aligned/unaligned inductance and stroke-averaged torque at three currents — sparse (2 rotor positions × 3 currents) but real bench data, not simulation.
  - Neither machine's source reproduces a B-H curve for its named material (M43 for the mapped 8/6 machine; M19 for the 6/4 machine); see the open item below.
  - **The 6/4 prototype also fails the validator's `self_starting` rule** (βs = 24° < 2π/(m·Nr) = 30° for m=3, Nr=4) and so cannot be built as-is through `RadialSRMParams`/the validator; see the M5 open item below.

- **12/8 or 24/16 FEMM reference:** Jiang's 24/16 PhD thesis machine (McMaster 2015) is the best available traction-class candidate — full geometry criterion (a) is **not** cleanly met (stack length is only approximate; rotor yoke thickness and rotor pole taper are missing; the 1 mm fillet the thesis reports is a pole-shoe fillet with no M1-topology counterpart, so neither `stator_fillet_radius` nor `rotor_fillet_radius` can represent it — see the parameter-mapping table). `rotor_outer_diameter` is *not* a gap: it is derivable (183 mm) from the thesis's stated 92 mm stator bore radius minus the 0.5 mm air gap. Selected provisionally with the remaining gaps documented in the parameter-mapping table below; the owner should try to obtain the companion 2017 IEEE Trans. Transportation Electrification journal paper (not present in `D:\y\srm`), which may close some gaps. **This machine also fails the validator's `self_starting` rule** (βs = 7.0°, βr = 7.2°, both < 2π/(m·Nr) = 7.5° for m=3, Nr=16) and so cannot be built as-is through `RadialSRMParams`/the validator either; see the M5 open item below.

- **Measured-data SRM reference (beyond TEAM 24):** Krishnan 6/4 prototype (above) is the primary pick. Azer's 12/8 MCSRM thesis (McMaster 2020) has genuinely measured dynamic **current** waveforms (dynamometer bench, oscilloscope-captured, multiple current/speed setpoints — Figs. 5.18–5.23) plus a DSP-computed torque *estimate*, driven by that measured current through an FEA-derived torque LUT rather than an independent torque sensor (Figs. 7.15–7.19; no torque transducer is described anywhere in the thesis). It's worth keeping as a secondary cross-check for current, but its geometry (pole arcs, yoke thickness, fill factor, lamination thickness, material grade) is too incomplete to build a mesh from, so it is not selected as a standalone `RadialSRMParams` source.

- **On criterion (c) specifically:** criterion (c) — measured ψ/T — **is** satisfied by a real candidate (Krishnan 6/4's measured inductance and stroke-averaged torque, Table 2.3). Azer's genuinely measured quantity is current only — its "torque" traces are a DSP-computed estimate, not an independent measurement (see the row above), so Azer does not independently satisfy (c). This is still not the "no candidate satisfies (c)" blocker condition described in the task brief, and nothing has been appended to spec §10 on that basis.

- **However, no single source in the library satisfies (a) + (b) + (c) together.** Every candidate with real measured data (Krishnan 6/4, Azer) only *names* its lamination grade (M19) without reproducing a B-H curve, and the best full-geometry traction candidate (Jiang 24/16) has neither a B-H curve nor measured data for the actual 24/16 prototype. This is a data-provenance gap, not a "no measured data exists" gap: `srmcore`'s own materials library (spec §5.3) is expected to source B-H curves for named catalog grades like M19 independently of the literature that merely cites the grade name, so this gap does not by itself block using these machines — but it means the audit cannot claim a single self-contained source for any selected machine. This is exactly the gap spec §10's M5 open item (iv) already records (library curves at confidence grade C resolve named catalog grades independently of the literature), so it is not a new spec §10 blocker, per the brief's criterion-(c)-specific escalation rule.

- **Buildability: none of the three selected machines is buildable through `RadialSRMParams` yet.** Listing only the fields `RadialSRMParams` requires (no schema default — see `src/srmcore/model/design.py`) that are still missing for each:
  - **Krishnan 8/6:** `fill_factor`, `slot_liner_thickness`, `coil_inner_clearance`.
  - **Krishnan 6/4:** `shaft_diameter`, `rotor_yoke_thickness` (the source's single unlabeled back-iron figure is assumed to be `stator_yoke_thickness` and not duplicated here), `fill_factor`, `slot_liner_thickness`, `coil_inner_clearance`. It also fails the `self_starting` validator rule (above), which blocks construction independently of these missing fields.
  - **Jiang 24/16:** `rotor_yoke_thickness`, `slot_liner_thickness`, `coil_inner_clearance`. It also fails the `self_starting` validator rule (above) and its 1 mm fillet cannot be represented by `stator_fillet_radius`/`rotor_fillet_radius` (both fields default to 0.0 and are pole-root-only, so the machine *would* pass schema construction with the fillet silently dropped rather than erroring — a fidelity loss, not a hard block, but worth the owner's attention).
  - None of these three machines can be handed to M5's FEMM/measured-comparison suites unmodified; each needs either owner-supplied assumptions for the missing fields or a validator ruling (self_starting) before it is usable. See the M5 open item in spec §10 (also linked from the top of this document).

## Parameter mapping for selected machines

All lengths in metres, all angles in radians, per `RadialSRMParams` (`src/srmcore/model/design.py`). "Stated" = given directly in the source (unit-converted only). "Derived (how)" = computed from other stated values using the `RadialSRMParams`/geometry relations in `design.py` (e.g. `rotor_outer_radius = bore_radius - air_gap`, `rotor_yoke_thickness = rotor_outer_radius - rotor_pole_height - shaft_radius`). "Not found" = absent from the source; a default from `RadialSRMParams`/`RegionMaterials` is suggested only where the field has a schema default (tapers, fillets, `materials`).

### Krishnan 8/6 design example (FEMM-comparison reference)

Source: Krishnan & Irwin, *Switched Reluctance Motor Drives*, CRC Press 2001, Ch. 2 §2.3.4 ("A second machine with 8/6 poles is considered...").

| Field | Value (SI) | Status |
|---|---|---|
| n_stator_poles | 8 | stated |
| n_rotor_poles | 6 | stated |
| n_phases | 4 | stated (8/6 standard 4-phase, q = Ps/2) |
| stator_outer_diameter | 0.190 m | stated ("Outer stator diameter 190 mm") |
| rotor_outer_diameter | 0.0996 m | derived: bore diameter (100.6 mm, stated) − 2×air_gap (2×0.5 mm) |
| air_gap | 0.0005 m | stated |
| stack_length | 0.200 m | stated |
| shaft_diameter | 0.028 m | stated |
| stator_pole_arc | 0.3142 rad | stated (18° → rad) |
| rotor_pole_arc | 0.3840 rad | stated (22° → rad) |
| stator_pole_taper | 0.0 | not found — schema default |
| rotor_pole_taper | 0.0 | not found — schema default |
| stator_yoke_thickness | 0.012 m | stated ("Stator back iron thickness 12 mm") |
| rotor_yoke_thickness | 0.016 m | derived: rotor_outer_radius (0.0498 m) − stated rotor pole height (0.0198 m) − shaft_radius (0.014 m). Cross-check: this also reproduces the stated stator pole height (32.7 mm ≈ stator_yoke_inner_radius (0.083 m) − bore_radius (0.0503 m)), giving confidence in the derivation. |
| stator_fillet_radius | 0.0 | not found — schema default |
| rotor_fillet_radius | 0.0 | not found — schema default |
| turns_per_pole | 77 | derived: Krishnan's stated `Tph` = 154 is turns per PHASE, wound over the 2 poles of that phase (8/6 has 4 phases × 2 poles/phase = 8 poles) — `turns_per_pole` = `Tph` / 2 = 77. (Corrected from an earlier draft of this audit, which took `Tph` as already per-pole and used 154; Eq. 2.7 `F1 = Tph·i` is the phase MMF across both series-connected poles of the phase, not the MMF contributed per individual pole.) |
| fill_factor | 0.22 | assumed (M5c): 77 turns × 1.588 mm² in a 550 mm² coil side |
| slot_liner_thickness | 0.0005 m | assumed (M5c) |
| coil_inner_clearance | 0.001 m | assumed (M5c) |
| lamination_thickness | — | **not found** |
| max_speed_rpm | 1500 | stated |
| materials.stator / materials.rotor | "M43" | stated ("Lamination material M43"); the M5c FEMM fixture uses M19 |
| materials.shaft | — | not found — schema default (`steel_1010`) |
| materials.coil | "copper" | implied (conductor area given; no explicit grade) — schema default |

### Krishnan 6/4 prototype (measured-data reference)

Source: same book, Ch. 2, dimensions table preceding Table 2.3.

| Field | Value (SI) | Status |
|---|---|---|
| n_stator_poles | 6 | stated |
| n_rotor_poles | 4 | stated |
| n_phases | 3 | stated (6/4 standard 3-phase, q = Ps/2) |
| stator_outer_diameter | 0.19 m | stated ("Stator diameter (outer) 19 cm") |
| rotor_outer_diameter | 0.10156 m | derived: the source's table row is literally labeled "Rotor diameter (bore) 10.206 cm" — read in context (a separate air gap is stated) this must mean the bore/stator-inner diameter, not the rotor's own OD; rotor_outer_diameter = 0.10206 m − 2×0.00025 m (air_gap) = 0.10156 m |
| air_gap | 0.00025 m | stated (0.025 cm) |
| stack_length | 0.06037 m | stated ("Core length 6.037 cm") |
| shaft_diameter | — | **not found** |
| stator_pole_arc | 0.418 rad | stated directly in radians |
| rotor_pole_arc | 0.628 rad | stated directly in radians |
| stator_pole_taper | 0.0 | not found — schema default |
| rotor_pole_taper | 0.0 | not found — schema default |
| stator_yoke_thickness | 0.010515 m | stated, but ambiguous: the table lists a single unlabeled "Back iron thickness 1.0515 cm" without saying stator or rotor; assumed stator here |
| rotor_yoke_thickness | — | **not found** (same ambiguity as above; not assumed equal without confirmation) |
| stator_fillet_radius | 0.0 | not found — schema default |
| rotor_fillet_radius | 0.0 | not found — schema default |
| turns_per_pole | 268 | derived: stated "Number of turns/phase 536" is turns per PHASE over the phase's 2 poles (6/4 has 3 phases × 2 poles/phase = 6 poles) — `turns_per_pole` = 536 / 2 = 268. (Corrected from an earlier draft of this audit, which used 536 directly; same phase-vs-pole distinction as the 8/6 row above.) |
| fill_factor | — | **not found** |
| slot_liner_thickness | — | **not found** |
| coil_inner_clearance | — | **not found** |
| lamination_thickness | — | **not found** (only wire gauge AWG #19 given, a conductor property) |
| max_speed_rpm | — | **not found** |
| materials.stator / materials.rotor | "M19" | stated ("Core material M19 steel") |
| materials.shaft | — | not found — schema default |
| materials.coil | "copper" | implied (AWG #19 wire) — schema default |

**Fails the validator's `self_starting` (Lawrenson) rule as published.** With m = 3 phases and Nr = 4 rotor
poles, `src/srmcore/model/validator.py` requires min(βs, βr) ≥ 2π/(m·Nr) = 30°. This machine's stated
βs = 0.418 rad = 24.0° < 30° (βr = 0.628 rad = 36.0° passes on its own but the rule takes the minimum), so
building this machine's stated geometry as-is through `RadialSRMParams`/the validator raises a `self_starting`
`InputError` — it cannot be constructed unmodified. The validator is not being changed for this; M5d builds the machine
inside `waive_rules("self_starting")` (decided 2026-09-30, spec §11).

**Second source (M5d, 2026-10-05).** The same machine is documented in P. N. Materu, PhD dissertation, Virginia Tech, 1989 (chair R. Krishnan), Table 1 p. 41 and Appendix A pp. 287–288: https://vtechworks.lib.vt.edu/server/api/core/bitstreams/42cbb685-1d45-43ad-b5c4-ff568e609f1c/content . It gives measured La, Lu and T_avg (the book's Table 2.3 values) and fills several gaps. Appendix A against the book table:

| Quantity | Book (Table 2.3 geometry) | Dissertation Appendix A |
|---|---|---|
| Bore (stator inner diameter) | 102.06 mm | 122.0 mm |
| Back iron | 10.515 mm | 10.15 mm |
| Shaft diameter | not given | 28.56 mm |
| Rotor pole height | not given | 27.25 mm |
| Core material | M19 | "E140 steel" (not identified, not in the library) |

Choice (M5d spec decision 1): the book bore and back iron, with shaft and rotor pole height from the dissertation (rotor yoke derived, 9.25 mm). The book bore reproduces Materu's own 2D FEA La at 1 A (Lu does not match: 45.7 vs 25.8 mH); the dissertation bore and back iron are a sensitivity (budget) row. Material is the M19 library curve, with steel_1010 as a crude bound. The measured T_avg is computed from the measured flux linkage (Materu p. 49), not from a torque sensor. Results: `docs/m5d-krishnan-results.md`.

Measured comparison data available for this machine (Table 2.3, for validation-report use, not `RadialSRMParams` fields): unaligned inductance, aligned inductance, and stroke-averaged electromagnetic torque, each given as Analytical / FEM / **Measured** at phase currents 1 A, 10 A, 20 A (measured values: 35.5/40.7/35.6 mH unaligned; 879/155/89 mH aligned; 0.90/20.30/41.60 N·m stroke-averaged torque).

### 24/16 traction SRM (FEMM-comparison reference, traction-class)

Source: James Weisheng Jiang, PhD thesis, McMaster University, Dec. 2015, Tables 4.1/4.2/6.2–6.4, §4.3.

| Field | Value (SI) | Status |
|---|---|---|
| n_stator_poles | 24 | stated |
| n_rotor_poles | 16 | stated |
| n_phases | 3 | stated |
| stator_outer_diameter | 0.264 m | stated (fixed to match 2010 Prius MG2 envelope) |
| rotor_outer_diameter | 0.183 m | derived: `RadialSRMParams.bore_radius = rotor_outer_radius + air_gap` (`src/srmcore/model/design.py`), inverted — stated stator bore radius 0.092 m minus stated air gap 0.0005 m gives rotor_outer_radius 0.0915 m, i.e. rotor_outer_diameter = 0.183 m. (Corrected from an earlier draft of this audit, which reported this as "not found" and cited only the thesis's initial 0.171–0.187 m rotor-OD sizing search range; the bore radius itself is stated directly and closes the gap.) |
| air_gap | 0.0005 m | stated |
| stack_length | ≈0.092 m | derived (approximate): 0.108 m total axial length (stated) − 0.016 m total end-turn allowance (stated) |
| shaft_diameter | 0.052 m | stated |
| stator_pole_arc | 0.1222 rad | stated (7.0° → rad, held fixed during rotor-arc sweep) |
| rotor_pole_arc | 0.1257 rad | stated (7.2° → rad, selected optimization Case C3) |
| stator_pole_taper | 0.1047 rad | stated (6° → rad, selected Case B7) |
| rotor_pole_taper | 0.0960 rad (5.5°) | assumed (M5c): middle of the initial 3–8° sizing range; no final selection reported |
| stator_yoke_thickness | 0.015 m | stated (selected Case B7) |
| rotor_yoke_thickness | 0.0455 m | assumed (M5c): 0.0915 − 0.026 (shaft radius) − 0.020 (assumed rotor pole height) |
| stator_fillet_radius | — | **not applicable — do not map.** The thesis's 1 mm fillet (Case D3) is a **pole-shoe** fillet (the corner where the flared pole tip meets the air gap), not a **pole-root** fillet. `stator_fillet_radius` in `RadialSRMParams` builds the pole-ROOT arc only (`src/srmcore/topology/radial.py`, tagged `*_pole_root`); the M1 topology has no pole-shoe geometry at all (poles are untapered rectangles/trapezoids with no flared tip) and no slot-wedge region. (Corrected from an earlier draft of this audit, which mapped the 1 mm value into `stator_fillet_radius` as if it were the pole-root fillet — it is not.) Recorded as an unrepresentable-in-M1 gap; see spec §10 M5 open item. |
| rotor_fillet_radius | — | **not found** (no rotor pole-root fillet is stated; the thesis's rotor pole-tip treatment, if any, is likewise a pole-shoe-class feature not represented in M1) |
| turns_per_pole | 15 | stated (15 turns/coil; also 10 parallel strands of 20 AWG wire per turn — not representable in this schema) |
| fill_factor | 0.54 | stated (target; 0.539–0.54 achieved for the selected design) |
| slot_liner_thickness | 0.0003 m | assumed (M5c) |
| coil_inner_clearance | 0.001 m | assumed (M5c) |
| lamination_thickness | 0.0001 m | stated (0.1 mm) |
| max_speed_rpm | 13500 | stated as the target/rated speed (matching the Prius motor); note the FEA torque-speed sweep (Fig. 6.17) extends to 14,000 rpm — the thesis is not fully consistent between "target" and "as-simulated" speed |
| materials.stator / materials.rotor | "10JNEX900" | stated (JFE Steel "Super Core", saturation flux density 1.91 T; no B-H curve reproduced) |
| materials.shaft | — | not found — schema default |
| materials.coil | "copper" | implied (20 AWG copper magnet wire) — schema default |

**Fails the validator's `self_starting` (Lawrenson) rule as published.** With m = 3 phases and Nr = 16 rotor
poles, `src/srmcore/model/validator.py` requires min(βs, βr) ≥ 2π/(m·Nr) = 7.5°. This machine's stated
βs = 7.0° and βr = 7.2° (Case C3) are both below 7.5°, so min(βs, βr) = 7.0° < 7.5° and building this
machine's stated geometry as-is through `RadialSRMParams`/the validator raises a `self_starting`
`InputError` — it cannot be constructed unmodified. The validator is not being changed for this; see the
new M5 open item in spec §10 for the owner's options.

**Unrepresentable-in-M1 gap — pole shoe and slot wedge.** The thesis's flared stator pole shoe (with its
1 mm shoe fillet, Case D3) and slot wedges have no counterpart in the M1 topology, which builds only plain
pole roots and open slots (`src/srmcore/topology/radial.py`); this cannot be closed by any `RadialSRMParams`
field and is recorded here as a geometry-fidelity gap for the owner, not a missing-data gap.

Because `rotor_yoke_thickness` and `rotor_pole_taper` are missing, and `stator_fillet_radius` /
`rotor_fillet_radius` cannot represent the source's pole-shoe fillet (above), this machine **cannot yet be
built as a concrete `RadialSRMParams` instance** without the owner making explicit engineering assumptions
for the remaining fields (e.g. mid-range of the stated rotor-pole-taper search range for `rotor_pole_taper`,
and an assumed value for `rotor_yoke_thickness`) — flagged, not resolved, here. (`rotor_outer_diameter` is no
longer missing: see the corrected derivation above.)
