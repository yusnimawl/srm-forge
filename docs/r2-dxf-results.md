# R2 DXF round trip: done check (8/6)

Spec §9 done check, run 2026-11-02 in the web app on the owner's cases.

1. The 8/6 reference case (10JNEX900, `full`) was exported and imported unedited: case `b8ee7fc2`, the same iron areas as the parametric outline.
2. In Onshape the owner added 8 yoke V-grooves, stator pole-side notches and 6 rotor lightening holes, trimmed the stator OD arc at the 0° notch and exported `trimmed.dxf` (fixture `tests/topology/fixtures/onshape_8_6_trimmed.dxf`, test `test_onshape_file_trimmed_in_cad_imports_cleanly`). The import gives no issues, 8 yoke holes and 6 rotor holes: case `e9f83310`. The untrimmed export (`onshape_8_6_edit.dxf`) is still refused with two open loops at the notch.
3. Both cases were evaluated at `full`. The before/after table (`GET /api/cases/{id}/compare`):

| Quantity | Before (`b8ee7fc2`) | After (`e9f83310`) | Change |
|---|---|---|---|
| Peak torque | 28.670 N·m | 28.590 N·m | −0.28 % |
| Flux linkage max | 2.5869 mWb | 2.5658 mWb | −0.82 % |
| La | 2.4253 µH | 2.4245 µH | −0.03 % |
| Lu | 0.25985 µH | 0.25983 µH | −0.01 % |
| Stator iron | 5.859 kg | 5.811 kg | −0.82 % |
| Rotor iron | 1.938 kg | 1.889 kg | −2.54 % |
| Total mass | 11.144 kg | 11.046 kg | −0.87 % |

The cases use the web form's default requirements (32 N·m), which the 8/6 does not meet, so the winding scan returned its least-bad winding, 1 turn on 2 paths. La, Lu and ψ are therefore at that winding; the comparison is like for like.

4. Validate on `full` (srmcore 0.7.0, 68 min with 4 workers): label **2D-verified**, every check passes.

| Check | Value | Limit |
|---|---|---|
| point_convergence_psi | 0.17 % | 0.5 % |
| point_convergence_torque | 0.02 % | 1 % |
| held_out_psi | 0.48 % | 0.5 % |
| held_out_torque | 0.26 % | 1.7 % |
| band_radius | 0.07 % | 1 % |
| map_matches_design, no_filled_points, held_out_converged | 0 | 0 |

Engine version, preset, map identity, material grade (B, B) and budget checks pass. Budget totals (worst case, end-winding corrected): La 5.7 %, Lu 6.7 %, peak torque 6.8 %, ψ_max 7.3 %; the material row (grade B) dominates.
