# R5 sources

Sources for the R5 thermal and rotor stress work (spec `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md`, §4.3). Everything below was read from the cited documents on 2026-11-07. Nothing is invented: where a value could not be found, this file says so and the library field stays `None`.

Grades: **A** measured on the owner's lot or a measured table, **B** a test or manufacturer figure, **C** typical, secondary or derived. Downloaded files were kept outside the repo; only URLs and pages are recorded.

## Summary

| # | Item | Source | Grade | Status |
|---|---|---|---|---|
| 1a | 10JNEX900 yield strength 570 MPa | Ou et al. 2021, p. 5 and Fig. 13 | B (tested, two samples, conditions not stated) | found |
| 1b | 10JNEX900 Young's modulus 200-210 GPa, Poisson ratio 0.33 | Ou et al. 2021, Table I (p. 2) | C (secondary table) | found |
| 1c | 10JNEX900 thermal conductivity 18.6 W/(m K) | Ou et al. 2021, Table I (p. 2) | C | found, direction not stated |
| 1d | 10JNEX900 through-stack conductivity, specific heat, expansion | none | - | **not found** |
| 1e | Test temperature and cutting method of the 570 MPa test | Ou et al. ref. [24] (ICEMS 2019) | - | **not found** (paper not reachable) |
| 2 | Copper k, c, expansion | National Bronze C11000 data sheet p. 2 | B | found |
| 3 | steel_1010 k, c, expansion, E, Poisson ratio, yield | Elgin Fasteners grade 1010 data sheet pp. 1-3 | C | found, cold-drawn condition |
| 4 | Kt of a shoulder fillet in tension | AmesWeb calculator page quoting Pilkey 2005 | C | formula found, book page not recorded; its 2h/D = 0 limit is used in the root model (section 5) |
| 5 | Rotor root and bore model, constants and validity range | derived from a converged 2D elastic FE sweep of this project, `tools/rotor_stress_sweep.py`, `docs/validation/rotor_sweep.json` | C (derived from this FE) | section 5 |

## 1. 10JNEX900

Source: J. Ou, Y. Liu, P. Breining, T. Gietzelt, T. Wunsch, M. Doppelbauer, "Experimental Characterization and Feasibility Study on High Mechanical Strength Electrical Steels for High-speed Motors Application", IEEE Trans. Ind. Appl. 57(1), 2021, pp. 284-293. Accepted manuscript (10 pages), https://publikationen.bibliothek.kit.edu/1000125982/128560422. Page numbers below are the manuscript's PDF pages.

- **Table I, p. 2** ("Properties comparison of 2605SA1 with 10JNEX900 [22], [27], [28]"): mass density 7490 kg/m3, Young's modulus 200-210 GPa, Poisson's ratio 0.33, yield strength 570 MPa, thermal conductivity 18.6 W/(m K), saturation induction 1.8 T, resistivity 82 uOhm cm, W10/400 5.7, thickness 0.1 mm, Vickers 200~300, maximum operating temperature 150 degC. The table cites refs. [22] (Liu et al., IEEE TIE 65(11), 2018, an amorphous-core paper), [27] (Wang et al., ECCE Asia 2011, amorphous cores) and [28] (Y. R. Wang, Manchester PhD thesis 2015, nanocrystalline cores). None of the three is about 10JNEX900, so the origin of E, Poisson's ratio and conductivity is not traceable from this paper. Grade C.
- **p. 5 and Fig. 13**: "The tested results of two 10JNEX900 samples ... stress-strain curves are quite similar ... The tested yield strength of them is 570 MPa." Fig. 13 is captioned "Tested mechanical strength of 10JNEX900 [24]". "10JNEX900 fails at plastic region", and "The samples are broken after the strain is higher than 14 %." The yield is therefore a test (two samples), not the owner's lot: grade B. The text gives no test temperature (the paper's only temperatures are about 25 degC for the B-H loops and 150 degC for the loss comparison) and no cutting method for the tensile samples. Not found.
- **Ref. [24]**: J. Ou et al., "Study of the electromagnetic and mechanical properties of a high-silicon steel for a high-speed interior PM rotor", ICEMS 2019, Harbin, pp. 1-4 (IEEE article 8921800; KIT record https://publikationen.bibliothek.kit.edu/1000105325). A search found the record but not the full text, and the KIT page has no PDF. Test temperature and cutting method stay unknown.
- **Second use of 570 MPa:** Ma et al., Materials 15(23), 8502, 2022 (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9736568/) states "the yield strength of 10JNEX900 is 570 Mpa" in its stress check, with no source for the value. It adds no independent measurement. The same paper says the prototype core was made by WEDM, but that is not stated for the tensile samples.
- **Not found:** through-stack conductivity, specific heat, thermal expansion coefficient. They are not in the JFE documents in `docs/sources/materials/` (f1e-002, f1g-001, f2e-001, Technical Report 21 p. 46: a text search for thermal, specific heat, expansion, conductivity, Young, tensile, yield and elastic found nothing relevant) or in Ou et al. 2021 or Ma et al. 2022. A web search for Fe-6.5Si values returned only other alloys, and no value was borrowed from them. Fields stay `None`. Missing values ask for JFE or the owner's lot (spec §4.3 list of requests).
- **Library entry:** `mechanical` yield 570 MPa (grade B), E 200 GPa (lower end of 200-210, the conservative end for growth, per the plan), Poisson ratio 0.33, `confidence` C, `strength_confidence` B, `brittle` false. `thermal` conductivity 18.6 (grade C); the table does not say whether it is in-plane or through-stack, so it goes in `conductivity` only and `conductivity_through_stack` stays `None`.
- **Gaps stated:** strength at temperature (not reported; the rotor runs hot), the effect of the owner's cutting process, and ultimate tensile strength (only in the Fig. 13 plot, not digitised).

## 2. Copper

Source: National Bronze Manufacturing, C11000 (Electrolytic Tough Pitch) data sheet, https://www.nationalbronze.com/pdfs/C11000.pdf, PDF page 2, "Physical Properties" (US customary). The sheet itself does not say where its values come from; the CDA page (alloys.copper.org) was under maintenance and the CDA fact sheet returned 403, so no CDA source was read.

| Quantity | As printed | SI used |
|---|---|---|
| Thermal conductivity | 226 Btu ft/(hr ft2 F) at 68 F | 391.1 W/(m K) (x 1.7307) |
| Specific heat | 0.092 Btu/lb/F at 68 F | 385.2 J/(kg K) (x 4186.8) |
| Expansion | 9.40e-6 per F (68-212 F); 9.60e-6 (68-392 F); 9.80e-6 (68-572 F) | 1.692e-5 per K (x 1.8, the 20-100 degC range) |

Grade B (a manufacturer data sheet, typical values). The library copper is the IEC annealed standard for resistivity; C11000 is the matching commercial grade (101 % IACS). Modulus of elasticity in tension 17000 ksi is on the same page but no copper `mechanical` block is added (not needed for R5a).

## 3. steel_1010

Source: Elgin Fasteners, "Carbon Steel Grade 1010 Data Sheet" (AISI 1010, UNS G10100, cold drawn), https://www.mwcomponents.com/uploads/Resource-Center/Elgin-Material-Sheets/Carbon-Steel-Grade-1010-Data-Sheet_Elgin-Fasteners.pdf, 3 pages. The table is a distributor copy of a MatWeb-type record. Grade C.

| Quantity | As printed | Page |
|---|---|---|
| Thermal conductivity | 49.8 W/m-K, "Typical steel" | 3 |
| Specific heat | 0.448 J/g-C at >= 100 degC, "condition unknown"; 0.498 at 150-200 degC and higher at higher temperature | 2-3 |
| Expansion | 12.2 um/m-C (0-100 degC); 13.5 (0-300); 14.2 (0-500) | 2 |
| Young's modulus | 205 GPa, "Typical for steel" | 2 |
| Poisson ratio | 0.29, "Typical for steel" | 2 |
| Yield | 305 MPa (44200 psi); ultimate 365 MPa | 1 |

Caveats: the library's `steel_1010` is the FEMM magnetic curve, whose condition is unknown, while this sheet is cold-drawn bar. Cold drawing raises the yield, so 305 MPa may be higher than an annealed lamination: use with the grade C allowance. The specific heat is quoted only for >= 100 degC (the first row, 0.448, is the lowest figure on the sheet); it is stored as the lowest value, and the block carries no `temperature_c` because the sheet states none for the other quantities either. Thermal data are typical values, the elastic constants are "typical for steel".

## 4. Stress concentration factor of a shoulder fillet in tension

Neither Peterson nor Roark was reachable. The formula below was read from the AmesWeb page "Stress Concentration Calculator - Shoulder Fillets in a Flat Bar", https://amesweb.info/stress-concentration-factor-calculator/shoulder-fillets-in-flat-bar.aspx, which gives as its reference Pilkey, W. D. (2005), Formulas for Stress, Strain, and Structural Matrices, 2nd ed., Wiley. The book page is not recorded: a page number "p. 156" for Peterson's Stress Concentration Factors (2nd ed., Pilkey 1997) is only an inference from the EES page "Rod with shoulder fillets under tension" (https://fchartsoftware.com/ees/mechanical_design/stress_concentration_factors/hs203.htm), which gives no formula, only one example, and says "rod", not flat bar. The source actually read is a calculator page quoting Pilkey 2005. Grade C. The coefficients and the D/d range still need checking against Peterson; gate V6 is the interim check.

Geometry (figure on the page): opposite shoulder fillets in a stepped flat bar; D = width of the wide part, d = width of the narrow part, h = step height = (D - d)/2 (drawn in the figure), r = fillet radius, L = length of the wide part, t = thickness. Load P in tension, nominal stress sigma_nom = P / (t d), sigma_max = Kt sigma_nom.

Kt = C1 + C2 (2h/D) + C3 (2h/D)^2 + C4 (2h/D)^3, with s = sqrt(h/r) and x = h/r:

| | 0.1 <= h/r <= 2.0 | 2 <= h/r <= 20 |
|---|---|---|
| C1 | 1.006 + 1.008 s - 0.044 x | 1.020 + 1.009 s - 0.048 x |
| C2 | -0.115 - 0.584 s + 0.315 x | -0.065 - 0.165 s - 0.007 x |
| C3 | 0.245 - 1.006 s - 0.257 x | -3.459 + 1.266 s - 0.016 x |
| C4 | -0.135 + 0.582 s - 0.017 x | 3.505 - 2.109 s + 0.069 x |

Validity as printed: the h/r ranges above, and L/D > -1.89 (r/d - 0.15) + 5.5 (a long enough wide part). The page gives no range for 2h/D. The code no longer checks this range: only C1 is used (section 5), and inside the section 5 box its argument x = H/r stays between 0.46 and 7.9 on the lattice and held-out designs, inside the printed 0.1 to 20. At 2h/D = 0 the fit returns C1, about 1 + sqrt(h/r), the semi-infinite-plate limit (1.32 at h/r = 0.1), a real value. The formula is for a plate in plane stress; a rotor bridge or pole root is not an isolated step, so it is a screening estimate.

Gate V6 showed the mapping d = pole width, D = pole pitch does not describe the root: nominal stress x Kt is 36 to 47 % below the FE. The full formula with that mapping is no longer used. Only its 2h/D = 0 limit C1 (one free shoulder of height h) is used, in section 5.

## 5. Rotor root and bore model

Grade C: derived from this project's FE, not from a measurement and not from a book. Code: `src/srmcore/post/rotor_stress.py`. Sweep: `tools/rotor_stress_sweep.py`. Data: `docs/validation/rotor_sweep.json`. Results: `docs/r5-thermal-results.md`.

### The FE behind it

Half-pole sector, plane stress, isoparametric P2 triangles on a gmsh second-order mesh with boundary nodes on the true arcs, u normal = 0 on both radial cuts, elements of fillet radius / 20, 40 and 80 on the fillet, stresses L2-projected to the continuous space and read at boundary nodes. Conditions: rho 7490 kg/m3, E 200 GPa, nu 0.33, 12 000 r/min, rotor radius 50 mm. All stresses scale with rho omega^2 R^2, so one speed and one size are enough: rescaling a design by 0.4 and 4 gives the same errors to 8 digits. Nu is nearly inert: on 37 designs at nu 0.25, 0.29 and 0.36 the root error moved by under 1 point and the bore error by under 1 point.

### The model

Notation: a shaft radius, b yoke outer radius, R rotor radius, t = b - a, N poles, d pole width at b, D = 2 pi b / N, r fillet radius, tau taper (rad, positive widens the root), h = R - b, F the pole force per depth, sigma_n = F / d.

Ring with stiff pole blocks. The free yoke arc between two poles has half angle gamma = pi/N - asin(d / 2b) - r / 2b. Taking the poles as blocks that do not rotate, equilibrium at mid span gives an axial force Nm = F / (2 sin(pi/N)) with no shear, and zero end rotation (the integral of M over the half arc is zero, bending energy only, Castigliano) gives, with Rm = (a + b)/2:

- M_mid = Nm Rm (1 - sin(gamma)/gamma), inner fibre in tension;
- M_end = Nm Rm (sin(gamma)/gamma - cos(gamma)), outer fibre in tension.

This derivation is ours. At gamma = pi/N it is the textbook ring with N point loads, (W R / 2)(1/sin a - 1/a); Roark was not reachable, so the limit was checked by a separate derivation and by a test, not against the book. Short arcs tend to a fixed-fixed beam, end moment twice the mid moment. Fibre stresses use the Winkler-Bach curved beam of a rectangular section: neutral radius rn = t / ln(b/a), sigma = M (distance from rn) / (t (Rm - rn) r_fibre), a standard result, cited from memory.

Rim relief: rho_r = 1 - c1 d / D. The pole roots stiffen the rim, so the annulus carries less of the rim load p = N F / (2 pi b). It applies in the bore stress and in the disc term of `gap_closure`.

Bore: sigma_bore = rho w^2 / 4 ((3 + nu) b^2 + (1 - nu) a^2) + 2 b^2 / (b^2 - a^2) p rho_r + c2 sigma(M_mid, inner).

Root: sigma_root = sigma_n c3 (D/d)^c4 ((L/r)^q - 1) + (sigma_rim + 1/2 sigma(M_end, outer)) C1(x) x^(-0.1 tau), where

- sigma_rim is the rotating annulus hoop stress at b with the rim load p;
- L = 1 / sqrt(1/d^2 + 1/(c5 t)^2), the shorter of the pole width and a share of the yoke;
- x = H / r with H = c6 d tanh(h / (c6 d)), the shoulder height the rim flow sees: the pole height for a short pole, limited for a long one;
- C1 is section 4 at 2h/D = 0, about 1 + sqrt(x);
- q = 0.4555 - 0.1 tau.

q is the corner exponent. Williams 1952 (J. Appl. Mech. 19, 526-528) gives a free corner of solid angle w the symmetric eigenvalue from sin(lambda w) = -lambda sin(w); the paper was not read, its citation was confirmed by a web search and the equation agrees with the 0.5445 usually quoted for 270 degrees. A test solves the equation: 1 - lambda = 0.4555 at 270 degrees, slope 0.1 per radian of solid angle. Fitting the slope freely on the sweep gave 0.093, which supports it.

The 1/2 was rounded from a free fit (0.48 to 0.60).

### Constants

| Symbol | Name in the code | Value | Meaning |
|---|---|---|---|
| c1 | `_BORE_RIM_RELIEF` | 0.049 | rim relief per unit d/D |
| c2 | `_BORE_BEND_GAIN` | 1.97 | gain on the mid-span ring bending at the bore |
| c3 | `_STEM_GAIN` | 0.682 | gain on the pole tension term |
| c4 | `_STEM_PITCH_POWER` | 0.265 | power of D/d |
| c5 | `_STEM_YOKE_SHARE` | 0.472 | share of t in L |
| c6 | `_SHOULDER_HEIGHT` | 0.197 | largest shoulder height / d |

Six fitted numbers, with no measured data in them. They come from `tools/rotor_stress_sweep.py fit` (the residual is the fourth power of the log error, so the cost is the eighth power; against 1.05 x FE, so errors centre on the high side) on 767 designs of the rounds below at commit 55ac728, when the fillet range still started at 0.01; the same command now gives other digits because it filters on the present box.

### Derivation and held-out rounds

First box (Latin hypercube rounds, seeds 1 to 7, R 50 mm):

| Round | Seeds, N_r | Role | Outcome |
|---|---|---|---|
| 1 | 1; 4, 6, 8, 16 | derivation of the form and the first constants | - |
| 2 | 2 and 3; 4, 6, 8, 16 and 10, 12 | held out for the first constants | root -4.98 to +13.71 %, bore pass, tip +15.78 %: FAIL on tip. Rim relief added to the growth; rounds 1 and 2 then became the derivation set |
| 3 | 4 and 5; same | held out for the present constants | root -5.40 %, one design of 337 at r/d 0.014: FAIL. The box was cut to r/d 0.015. Constants unchanged |
| 4 | 6 and 7; same | held out for the present constants | passed, but a Latin hypercube never reaches the corners |

Review of the first box: lattices of its corners gave root -10.9 to +24.8 %, bore -6.1 to +19.2 %, peak -10.9 %, confirmed by an independent NGSolve FE. Low roots came from fillets that nearly meet on the rim and from the smallest fillets, bore out of band from yokes at 0.5 of the tip chord. That review spent the first box.

Present box (commit 92b3fcc, constants unchanged since 55ac728):

| Step | Commit | Designs | Result |
|---|---|---|---|
| Lattice over a wider box, R 0.5 m, to choose the box (seen) | - | 16 275 | the limits below |
| `tools/rotor_stress_sweep.py lattice`: 5 x 6 x 6 x 3 x 7 per pole count, points outside moved along the line to the centre onto a joint limit (seen) | 92b3fcc | 16 338 | root -3.44 to +12.87 %, bore -3.97 to +14.36 %, tip -9.40 to +11.20 % |
| Held-out list `heldout 11`: 160 corners, 80 taper 0 corners, 300 boundary rays, 300 face points, 607 interior | 37303cd, before any FE on it | 1447 | |
| FE of that list, no change to box or constants | 82e32a1 | 1447 | PASS: root -3.44 to +11.81 %, bore -3.52 to +13.29 %, tip -7.77 to +10.76 %, peak -3.44 % |

8/6, 12/8 and 24/16 took no part in any fit; their FE was seen before the fit only for 8/6 and 12/8, in the load split.

### Validity range

Outside it `root_stress_concentration` returns None and `rotor_stress` gives status `kt_out_of_range`, the nominal root stress and no safety factor. Each limit, joint ones too, is tested just inside and just outside (tests/post/test_rotor_stress.py).

| Ratio | Range |
|---|---|
| N_r | one of 4, 6, 8, 12, 16 |
| shaft diameter / rotor diameter | 0.25 to 0.45 |
| rotor pole arc / (2 pi / (q N_r)), q the swept phase count of that pole count (4: 3, 6: 4, 8: 3, 12: 3, 16: 3) | 1.0 to 1.7 |
| yoke thickness / pole tip chord | 0.55 to 1.15 |
| taper | -1.5 to +1.5 degrees |
| fillet radius / pole width at the root | 0.025 to 0.2 |
| free ring half span gamma / half pitch | at least 0.1 |
| free ring half arc gamma b / fillet radius | at least 1 (joint limit: the fillets may not nearly meet on the rim) |

Search coverage: of 1200 `sample_candidates` designs (seed 5) given a fillet of 0.03 to 0.05 of the pole width, 980 to 996 (82 to 83 %) read `ok`; 123 fall below the yoke limit and 81 to 97 on the free span. By pole count at 0.03: 4 poles 88 %, 6 poles 89 %, 8 poles 82 %, 16 poles 72 %. The generator itself leaves `rotor_fillet_radius` at 0, so its candidates read `no_fillet`.
