# Reference machines for validation (M1 audit)

Criteria: (a) full geometry, (b) B-H data of the lamination, (c) MEASURED ψ(θ,i) and/or static T(θ,i).

Library searched: `D:\y\srm` (read-only, ~60 PDFs). Exact filenames confirmed via directory listing.

| Candidate | Source file | Pages / figures | Topology | (a) geometry | (b) B-H | (c) measured ψ / T | Qualifies | Notes |
|---|---|---|---|---|---|---|---|---|
| TEAM Problem 24 | ngsolve.github.io TEAM-24 page + original TEAM report (Allen & Rodger, Univ. of Bath, fetched from `compumag.org/.../problem24.pdf`, linked from the NGSolve page) | Fig. 1–2 (geometry), Fig. 3 & Table I (B-H), Figs. 5–9 & Tables II–VI (measured step-voltage/current/torque/flux/B) | Single-pole-pair SRM-like rig (locked rotor at 22°, not a conventional multi-pole rotating SRM) | **Yes** — full dimensions in Fig. 1 (stator Ø209.0 mm, rotor Ø102.1 mm outer / Ø50.8 mm shaft, rotor pole height 12.7 mm, axial length 25.4 mm) and Fig. 2 (two 350-turn coils, 3.09 Ω total, wire Ø1 mm, coil section 24×17 mm²) | **Yes** — Table I / Fig. 3: measured EN9 medium-carbon-steel initial magnetization curve (Magnet-Physik Remagraph RE3 BH tester up to ~2 T, extended to 2.5 T by Lucas A.V.S.D.), 21 tabulated (H, B) points | **Yes** — Figs. 5–9 / Tables II–VI: measured step voltage (23.1 V), coil current, torque (piezoelectric force link, radius 0.268 m), rotor-pole search-coil flux, and Hall-probe air-gap flux density, all vs. time, for a single locked-rotor step-voltage test | **Yes, for its own scope** | Not a standard multi-pole rotating SRM — no `RadialSRMParams` mapping is produced for it (see Decision). Use directly per spec §2.3 (magnetostatic/current-rise scope, TEAM24 test suite 5). |
| Krishnan 8/6 design example | *Switched Reluctance Motor Drives* (Krishnan & Irwin, CRC 2001), Ch. 2 §2.3.4 "Results and Comparison" (file `0838_pdf_c02.pdf`, "second machine with 8/6 poles" table) and a related 8/6 prototype in Ch. 3 §3.8 pole-base-shaping study (file `0838_pdf_c03.pdf`) | Ch.2 table immediately after Table 2.3; Ch.3 table before Fig. 3.23 | 8/6, 4-phase | **Yes** (Ch.2 table: 8 stator/6 rotor poles, 5 hp, stator pole arc 18°, rotor pole arc 22°, air gap 0.5 mm, OD 190 mm, bore 100.6 mm, stack 200 mm, shaft 28 mm, 1500 rpm, stator back-iron 12 mm, stator pole height 32.7 mm, rotor pole height 19.8 mm, turns/phase 154, conductor 1.588 mm², rated 13 A) | **Not found** — lamination named "M43" (Ch.2) or "M19 steel" (Ch.3 variant), but neither chapter reproduces a B-H table/plot for it | **No — FEM only.** Ch.2 gives only "Finite Element Analysis (mH) vs. Analytical (mH)" for aligned/unaligned inductance (65.41/66.79 and 11.35/11.38 mH) — no bench measurement. Ch.3's 8/6 pole-shaping study (Fig. 3.23) is FEM-only too. | **No** (fails b, c) | Used per spec §2.3/§8.2 as the **FEMM-comparison** reference only (that role does not require measured data). See the companion **Krishnan 6/4 prototype** below, found in the same chapter, which does have genuine measured data. |
| Krishnan 6/4 prototype (supplementary — not in brief's original list, added because it directly serves the "measured SRM reference" decision) | Same book, Ch. 2, Table 2.3 "Comparison of Inductance by Various Methods" and preceding text (file `0838_pdf_c02.pdf`) | Table 2.3 and the dimensions table immediately before it | 6/4, 3-phase | **Mostly yes** (stator OD 19 cm, bore/stator-inner diameter 10.206 cm, core length 6.037 cm, air gap 0.025 cm, back-iron thickness 1.0515 cm [table does not say stator vs. rotor], stator pole arc 0.418 rad, rotor pole arc 0.628 rad, turns/phase 536, wire AWG #19, core M19 steel); shaft diameter and speed rating **not found** | **Not found** — "M19 steel" named, no curve reproduced | **Yes** — Table 2.3: measured unaligned inductance, aligned inductance, and average electromagnetic torque at three currents (1 A, 10 A, 20 A: e.g. 35.5/879/0.90, 40.7/155/20.30, 35.6/89/41.60 — measured columns), alongside analytical and FEM columns for comparison | **No** (fails b only) | Nearest 8/6-class machine in the library with real bench data (sparse — only 2 rotor positions × 3 currents, not a full ψ(θ,i) map). Selected as the primary **measured-data reference**. |
| Mak MASc thesis machine | `Mak_Christopher_See-Hon_2020aug_MASc (1).pdf` — "18/12 Switched Reluctance Motor Design for a Mild-Hybrid Electric Powertrain Application" (McMaster, 2020) | Table 5.7 p.77 (finalized geometry); Fig. 3.6 p.34 (generic illustrative curve only) | 18/12, 3-phase (belt-alternator-starter traction class) | **Partial** — pole counts, phases, OD 170 mm, rotor OD 110.6 mm, air gap 0.5 mm, stack 62.5 mm, pole arcs 11°/11°, stator/rotor taper 0.8°/2°, pole-tip/root fillets (1/0 mm stator, 1/0.5 mm rotor). **Not found**: yoke thicknesses (not a clean concept — spoked rotor), fill factor, slot liner thickness, coil inner clearance, lamination thickness, max speed (only a ~1500–1667 rpm idle target), lamination material grade. Shaft found separately (4340 steel, non-laminated). | **Not found** — Fig. 3.6 is a generic textbook flux-linkage illustration borrowed from a different thesis (Jiang's), not this machine's own material data; no steel grade is ever named for the core | **No — FEM only.** Entirely a JMAG/Matlab design study; Ch.7 "Future Works" explicitly lists prototype build/test as unfinished. No bench data anywhere. | **No** | 18/12 is traction-class, not 8/6-class. Excluded from all three selection slots. |
| Azer PhD thesis machine | `Azer_Peter_202006_PhD.pdf` — "Mutually Coupled Switched Reluctance Machines: Fundamentals, Modeling, and Control" (McMaster, 2020) | Table 5.1 p.55 (geometry); Figs. 5.18–5.23 pp.85–89 & Figs. 7.15–7.19 pp.147–154 (measured current/torque) | 12/8, 3-phase (small 2 kW lab prototype, originally a conventional SRM rewound for mutually-coupled operation — not traction-scale despite the 12/8 count) | **Partial** — pole counts, phases, stator OD 136 mm, rotor OD 83 mm, air gap 0.3 mm, stack 70 mm, turns/phase 28 (ambiguous shaft: 38 mm EM cutout vs. 70 mm mechanical cutout in the table). **Not found**: pole arcs, tapers, yoke thicknesses, fillets, fill factor, slot liner, coil clearance, lamination thickness, lamination material grade (never named anywhere in the thesis) | **Not found** | **Partial — genuinely measured, but dynamic not static.** Ch.5 §5.4 (Figs. 5.18–5.23, Table 5.5 p.85): measured phase current on a dynamometer-loaded bench at stated (id,iq) setpoints, 500–1500 rpm. Ch.7 §7.5 (Figs. 7.15–7.19, Tables 7.1–7.2 pp.149,155): measured "electromagnetic torque" oscilloscope traces at 1000/1500 rpm, 3 N·m reference, for stated (id,iq) currents. No static locked-rotor T(θ) or ψ(θ,i) sweep. | **No** (fails a, b) | Has real measured torque/current data but geometry is too incomplete to build a mesh from; kept as a secondary cross-check candidate only, not selected as the primary measured reference. |
| 24/16 traction SRM | `THREE-PHASE 24 16 SWITCHED RELUCTANCE MACHINE FOR HYBRID ELECTRIC POWERTRAINS DESIGN AND OPTIMIZATION.pdf` — James Weisheng Jiang PhD thesis (McMaster, Dec. 2015, supervisor Ali Emadi) | Table 4.1 p.73, Table 4.2 p.80 (initial sizing), Tables 6.2–6.4 pp.138–146 (optimized/selected geometry), §4.3 p.78 (lamination) | 24/16, 3-phase (traction, sized to match the 2010 Prius MG2 envelope) | **Partial, substantial but incomplete** — stator OD 264 mm, air gap 0.5 mm, shaft 52 mm, stator pole arc 7.0°, rotor pole arc 7.2° (Case C3), stator pole taper 6° (Case B7), stator yoke 15 mm (Case B7), stator pole-shoe fillet 1 mm (Case D3), turns/pole 15 (10 strands, 20 AWG), fill factor ≈0.54, lamination 0.1 mm. **Not found / not finalized**: rotor OD (only an initial 171–187 mm search range, no final value), stack length (only derivable ≈92 mm active from 108 mm total minus 16 mm end-turn allowance), rotor pole taper (only an initial 3–8° range), rotor yoke thickness, rotor fillet radius, slot liner thickness, coil inner clearance, shaft/coil material grade | **Not found** — lamination named "10JNEX900" (JFE Steel "Super Core"), saturation flux density 1.91 T stated, but no B-H curve/table reproduced (cites a manufacturer datasheet by reference only) | **No — FEM only for the 24/16 machine itself.** Entire thesis is JMAG FEA; no 24/16 prototype was built. (A *different*, smaller 12/8 SRM elsewhere in the same thesis, Ch.5 Fig. 5.5 p.96 and Figs. 5.22–5.24 pp.120–123, WAS bench-validated for flux linkage vs. rotor position and current waveforms — but that 12/8 machine's own geometry is not given, so it can't substitute.) | **No** (fails b, c; a is incomplete) | Best available 24/16 candidate in the library. Companion journal paper (Jiang, Bilgin, Emadi, IEEE Trans. Transportation Electrification 2017 — describing the same machine) is cited but not present in this library; it might close some of the (a) gaps. |
| 24/16 NVH machine | `Prediction of acoustic noise and vibration of a 24 16 traction switched reluctance machine.pdf` — Liang, Jiang, Callegaro, Bilgin, Dong, Reeves, Emadi, *IET Electrical Systems in Transportation* 10(1), 2020 | Table 1 p.36 (geometry subset), Table 2 p.39 (structural FEA properties, not magnetic), Figs. 21–22 p.42 (hammer-test measurement) | 24/16, 3-phase — **confirmed same physical prototype** as the "24/16 traction SRM" row above (paper's ref. [1] is Jiang/Bilgin/Emadi 2017; Table 1 is explicitly captioned as reproducing that paper's numbers; same McMaster MARC research group) | **Mostly not found** — only reproduces a headline subset from the companion paper: stator OD 264 mm, air gap 0.5 mm, stack (axial active length) 108 mm, fill factor 0.54, lamination 0.1 mm, max speed 13,500 rpm. All pole/yoke/fillet/turns/clearance fields not found here (not this paper's subject). | **Not found** — no B-H curve at all; Table 2 gives only *structural* material properties (density, Young's modulus, Poisson's ratio) for stator core, coils, and housing, used for modal/acoustic FEA, not magnetic FEA | **No, for ψ/T — only structural.** Sole physical measurement is a hammer (impact-modal) test on the dyno-mounted prototype (Fig. 21, p.42): measured natural frequencies 1735 Hz and 4852 Hz (Fig. 22b) vs. simulated 1782/4784 Hz (Table 3, p.41). All sound-pressure-level and vibration-under-operation results (Figs. 14–20) are simulated ("virtual microphones"/ACTRAN), not measured. No measured ψ(θ,i) or T(θ,i) anywhere. | **No** | Data-quality note: this paper names the lamination "NO10" (Cogent Power Inc.) while the companion 2015/2017 thesis names it "10JNEX900" (JFE Steel) for the same physical machine — an unresolved inconsistency between the two sources about the same prototype's core material. |

## Decision

- **8/6 (or nearest) FEMM + measured reference:** Two machines from the same book, since no single 8/6-class source in the library has both.
  - **FEMM-comparison reference:** Krishnan 8/6 design example (5 hp, 190 mm OD, M43 core; Krishnan & Irwin 2001, Ch. 2 §2.3.4). Full geometry given; the book's own FEM-vs-analytical comparison (no bench data) is exactly what spec §8.2 suite 4 needs.
  - **Measured-data reference (nearest topology):** Krishnan 6/4 prototype, same book (Table 2.3). Genuinely measured aligned/unaligned inductance and average torque at three currents — sparse (2 rotor positions × 3 currents) but real bench data, not simulation.
  - Neither machine's source reproduces a B-H curve for its named material (M43 / M19); see the open item below.

- **12/8 or 24/16 FEMM reference:** Jiang's 24/16 PhD thesis machine (McMaster 2015) is the best available traction-class candidate — full geometry criterion (a) is **not** cleanly met (rotor OD was never finalized to a single value, only an initial 171–187 mm search range; stack length, rotor yoke thickness, rotor pole taper, and rotor fillet radius are also missing or only approximate). Selected provisionally with these gaps documented in the parameter-mapping table below; the owner should try to obtain the companion 2017 IEEE Trans. Transportation Electrification journal paper (not present in `D:\y\srm`), which may close some gaps.

- **Measured-data SRM reference (beyond TEAM 24):** Krishnan 6/4 prototype (above) is the primary pick. Azer's 12/8 MCSRM thesis (McMaster 2020) has genuinely measured dynamic current and torque waveforms (dynamometer bench, oscilloscope-captured, multiple current/speed setpoints — Figs. 5.18–5.23, 7.15–7.19) and is worth keeping as a secondary cross-check, but its geometry (pole arcs, yoke thickness, fill factor, lamination thickness, material grade) is too incomplete to build a mesh from, so it is not selected as a standalone `RadialSRMParams` source.

- **On criterion (c) specifically:** criterion (c) — measured ψ/T — **is** satisfied by real candidates (Krishnan 6/4, and separately Azer), so this is not the "no candidate satisfies (c)" blocker condition described in the task brief, and nothing has been appended to spec §10 on that basis.

- **However, no single source in the library satisfies (a) + (b) + (c) together.** Every candidate with real measured data (Krishnan 6/4, Azer) only *names* its lamination grade (M19) without reproducing a B-H curve, and the best full-geometry traction candidate (Jiang 24/16) has neither a B-H curve nor measured data for the actual 24/16 prototype. This is a data-provenance gap, not a "no measured data exists" gap: `srmcore`'s own materials library (spec §5.3) is expected to source B-H curves for named catalog grades like M19 independently of the literature that merely cites the grade name, so this gap does not by itself block using these machines — but it means the audit cannot claim a single self-contained source for any selected machine. Recorded as an explicit caveat here rather than as a spec §10 blocker, per the brief's criterion-(c)-specific escalation rule.

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
| turns_per_pole | 154 | stated ("Turns per phase 154"; Krishnan's `Tph` is used as per-pole turns throughout his flux-path/mmf derivations, e.g. Eq. 2.7 `F1 = Tph·i` for one excited pole) |
| fill_factor | — | **not found** |
| slot_liner_thickness | — | **not found** |
| coil_inner_clearance | — | **not found** |
| lamination_thickness | — | **not found** |
| max_speed_rpm | 1500 | stated |
| materials.stator / materials.rotor | "M43" | stated ("Lamination material M43") |
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
| rotor_outer_diameter | 0.10156 m | derived: stated bore/stator-inner diameter (10.206 cm) − 2×air_gap (2×0.025 cm) |
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
| turns_per_pole | 536 | stated ("Number of turns/phase 536"), same per-pole-turns convention as above |
| fill_factor | — | **not found** |
| slot_liner_thickness | — | **not found** |
| coil_inner_clearance | — | **not found** |
| lamination_thickness | — | **not found** (only wire gauge AWG #19 given, a conductor property) |
| max_speed_rpm | — | **not found** |
| materials.stator / materials.rotor | "M19" | stated ("Core material M19 steel") |
| materials.shaft | — | not found — schema default |
| materials.coil | "copper" | implied (AWG #19 wire) — schema default |

Measured comparison data available for this machine (Table 2.3, for validation-report use, not `RadialSRMParams` fields): unaligned inductance, aligned inductance, and average electromagnetic torque, each given as Analytical / FEM / **Measured** at phase currents 1 A, 10 A, 20 A (measured values: 35.5/40.7/35.6 mH unaligned; 879/155/89 mH aligned; 0.90/20.30/41.60 N·m average torque).

### 24/16 traction SRM (FEMM-comparison reference, traction-class)

Source: James Weisheng Jiang, PhD thesis, McMaster University, Dec. 2015, Tables 4.1/4.2/6.2–6.4, §4.3.

| Field | Value (SI) | Status |
|---|---|---|
| n_stator_poles | 24 | stated |
| n_rotor_poles | 16 | stated |
| n_phases | 3 | stated |
| stator_outer_diameter | 0.264 m | stated (fixed to match 2010 Prius MG2 envelope) |
| rotor_outer_diameter | — | **not found** (only an initial 0.171–0.187 m sizing search range; no finalized single value in the thesis) |
| air_gap | 0.0005 m | stated |
| stack_length | ≈0.092 m | derived (approximate): 0.108 m total axial length (stated) − 0.016 m total end-turn allowance (stated) |
| shaft_diameter | 0.052 m | stated |
| stator_pole_arc | 0.1222 rad | stated (7.0° → rad, held fixed during rotor-arc sweep) |
| rotor_pole_arc | 0.1257 rad | stated (7.2° → rad, selected optimization Case C3) |
| stator_pole_taper | 0.1047 rad | stated (6° → rad, selected Case B7) |
| rotor_pole_taper | — | **not found** (only an initial 3–8° sizing range; no final selection reported) |
| stator_yoke_thickness | 0.015 m | stated (selected Case B7) |
| rotor_yoke_thickness | — | **not found** |
| stator_fillet_radius | 0.001 m | stated (pole-shoe fillet, selected Case D3) |
| rotor_fillet_radius | — | **not found** |
| turns_per_pole | 15 | stated (15 turns/coil; also 10 parallel strands of 20 AWG wire per turn — not representable in this schema) |
| fill_factor | 0.54 | stated (target; 0.539–0.54 achieved for the selected design) |
| slot_liner_thickness | — | **not found** |
| coil_inner_clearance | — | **not found** |
| lamination_thickness | 0.0001 m | stated (0.1 mm) |
| max_speed_rpm | 13500 | stated as the target/rated speed (matching the Prius motor); note the FEA torque-speed sweep (Fig. 6.17) extends to 14,000 rpm — the thesis is not fully consistent between "target" and "as-simulated" speed |
| materials.stator / materials.rotor | "10JNEX900" | stated (JFE Steel "Super Core", saturation flux density 1.91 T; no B-H curve reproduced) |
| materials.shaft | — | not found — schema default |
| materials.coil | "copper" | implied (20 AWG copper magnet wire) — schema default |

Because `rotor_outer_diameter`, `rotor_yoke_thickness`, `rotor_pole_taper`, and `rotor_fillet_radius` are all missing, this machine **cannot yet be built as a concrete `RadialSRMParams` instance** without the owner making explicit engineering assumptions for those four fields (e.g. mid-range of the stated search boxes) — flagged, not resolved, here.
