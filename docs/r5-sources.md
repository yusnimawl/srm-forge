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
| 6a | Gnielinski turbulent duct Nu, friction factor, range, scatter | Jacimovic et al., FME Transactions 54, 391-401, 2026, Eq. (7) and (8), printed pp. 392 and 393 (open access; read) | C (a paper that prints Gnielinski's equation and quotes its range and the 10 % from Shah and Sekulic 2003) | formula, range and 10 % found in a read document; the 1976 original was not read |
| 6b | Laminar fully developed Nu, rectangular duct | `ht` documentation citing Shah and London 1978 (square, constant heat flux, 3.610 only; page summary) | C | formula known, primary not read; **left out of defaults**, laminar jacket refused |
| 6c | Air-gap Nu for a salient rotor, 8/6; second cited correlation | Romanazzi and Howey 2015, EVER, pp. 2 and 6 (arXiv 1502.05902); Faiz 2009 Eq. (6), PDF p. 4 | B (CFD fit, one geometry); C (flat plate, Incropera) | formulas and ranges found; no scatter stated; the area A in Ta_m is not defined and the digits 1967 and 0652 are in the arXiv LaTeX source as printed, unresolved |
| 6d | Natural convection, horizontal cylinder and vertical plate; air properties | Faiz 2009 Eq. (1) to (5) and Table III, PDF pp. 3 and 4 (cites Markovic et al. 2006 [17]); Boglietti et al. 2009 Sec. VI-A and VI-C for a second end-space route | C | formulas and air properties found in a read paper; no Ra range printed, accuracy **not found** |
| 6e | Oil spray on end windings, h | Hoffmann et al. (KIT, shaft spray, model fluid); Shams Ghahfarokhi et al. 2024 (nozzles, one hairpin conductor) | B (measured, single rigs) | two measured h ranges found, 190 to 910 and 1100 to 4800 W/(m2 K), not transferable between rigs |
| 6f | Shaft oil cooling to the rotor, h | none | - | **not found** |
| 6g | Slot oil channel, h | Marquez-Fernandez 2018 prints no h | - | **not found**; water in a duct is covered by 6a |
| 6h | Stator to housing contact, equivalent gap | Boglietti, Cavagnino, Staton et al., IEEE Trans. Ind. Electron. 56(3), 871-882, 2009, Sec. VI-E, printed pp. 879 and 880 (survey; Staton 2005 itself was not reachable) | C (survey, no table, measured basis for industrial induction motors) | 0.01 to 0.08 mm found, 0.03 mm as the stated default |
| 6i | Slot liner conductivity | DuPont Nomex 410 technical data sheet K-20612-3 (06/20), Table IV, PDF p. 5; Faiz 2009 Table II p. 2 | B (manufacturer, ASTM E1530 at 150 degC); C | Nomex 0.103 to 0.175 W/(m K) by thickness; Faiz 0.076 |
| 6j | Impregnation resin conductivity | Marquez-Fernandez 2018 p. 8 | B | 0.6 to 1 W/(m K) |
| 6k | Aluminium housing alloy | Faiz 2009 Table II (frame, aluminium) | C | 177 W/(m K); the 6061-T6 figure was deleted (no document opened) |
| 6l | Coolants | MEGlobal Ethylene Glycol Product Guide pp. 18 to 20 and 28 (50 wt % glycol, 40 to 100 degC); ATF | B (glycol) / - | glycol found; ATF cp and conductivity **not found** |
| 6m | Cross-wire conductivity (Milton, Hashin-Shtrikman) | Marquez-Fernandez 2018 Eq. (5) and (6), pp. 7 and 8 | B | formulas found; xi found for fill 0.37 only |
| 6n | Lamination conductivity scatter | none read; grade-C allowance of `srmapp.losses.LOSS_GRADE_ALLOWANCE["C"]` | C (rule, no measurement) | no scatter found; unfavourable end 18.6 x (1 - 0.25) = 13.95 W/(m K) by the plan's grade-C rule |
| 7 | Band for every budget row that needs one | sections 6 and 7 | - | section 7 |
| 8 | V3 record (Marquez-Fernandez 2018) | pp. 2, 3, 8 and 9 | B | section 8; the Milton value 2.41 is reproduced, the 0.47 point (3.11) is not (xi is given for 0.37 only); recorded, nothing changed |

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

## 6. Cooling correlations and properties (R5b)

Read on 2026-11-09, with a fix round the same day. Local PDFs (IEEE copyright, git-ignored, never committed): Marquez-Fernandez 2018 and Faiz 2009, read with PyMuPDF from a scratch directory. Open documents downloaded to scratch directories and read the same way: Romanazzi and Howey 2015, Jacimovic et al. 2026, Boglietti et al. 2009 (survey), Hoffmann et al., Shams Ghahfarokhi et al. 2024, the MEGlobal guide and the DuPont Nomex 410 data sheet. Reached only as a web search result or a page summary and **not used for any default**: the `ht` documentation (square-duct laminar Nu), the Bobolea `htcie` page, the Engineers Edge table, the SynFlex page (agrees with DuPont Table IV), MatWeb (deleted), the NREL lamination papers, the Anton Paar and Motul oil sheets. Not reachable (403, bot block or connection refused): Staton, Boglietti and Cavagnino 2005, the NREL papers, Idoughi et al. 2011 (HAL), Incropera and Gnielinski 1976 themselves. Where a value comes from a search-result summary and not from an opened document, the entry says so. Page numbers are PDF pages of the file read unless "printed" is written.

### 6.1 Forced convection in a duct

**Gnielinski, turbulent (item 6a).** Read in a document: B. Jacimovic et al., FME Transactions 54, 391-401, 2026 (open access, https://simlab.mas.bg.ac.rs/_media/istrazivanje/fme/vol54/3/1_b._jacimovic_et_al.pdf), PDF pages 2 and 3 (printed pp. 392 and 393). Eq. (8) as printed: Nu = [(f_W/8)(Re - 1000) Pr / (1 + 12.7 sqrt(f_W/8) (Pr^(2/3) - 1))] [1 + (d/L)^(2/3)] phi_t, with f_W the smooth-pipe friction factor of Eq. (7), f_W = [0.79 ln(Re) - 1.64]^-2 (Filonenko 1954; the paper says Eq. (7) is valid for Re 1e4 to 5e6), and phi_t = (Pr_b/Pr_w)^0.11 for liquids (Eq. 9, ratio 1 to 10). Ranges and accuracy, as the paper states them (p. 393): the author himself gives Re 2300 to 1e6, Pr 0.5 to 500 and L >= d (Gnielinski, Int. Chem. Eng. 16, 359-368, 1976); another handbook (Ebadian and Dong, Rohsenow et al. 1998) recommends 2300 to 5e6; Shah and Sekulic (2003) do not recommend it for the critical range Re 2000 to 4000 and put its overall accuracy at 10 %; Gnielinski's 2013 paper (Int. J. Heat Mass Transfer 63, 134-140) limits it to Re 4000 to 1e6. The 1976 original and Incropera were not read. **Recorded for the code:** the formula above; validity Re 4000 to 1e6 (the narrowest range any of the quoted statements gives, and the author's own in 2013), Pr 0.5 to 500, L >= d; scatter 10 % (grade C, quoted second-hand from Shah and Sekulic). The factor [1 + (d/L)^(2/3)] and phi_t are in the printed equation; the plan decides whether the code includes them or omits them as a stated simplification, and the 10 % band covers the omission only if the plan says so. Earlier entries of this file that quoted the Bobolea `htcie` page (range 3000 to 5e6, Pr to 2000) are superseded: that page was a search result and is not used for a default.

**Laminar, fully developed (item 6b).** Found: circular tube Nu 3.66 (constant wall temperature) and 4.36 (constant heat flux) on the `htcie` page, which cites Shah and London 1978 (*Laminar Flow Forced Convection in Ducts*, Academic Press) without a page. For a rectangular duct, the `ht` documentation (`Nu_laminar_rectangular_Shan_London`, citing the same book and Shah and London 1971 Table 42) says the model assumes constant wall heat flux on all sides and that a square duct gives Nu 3.610224. **Not found:** Nu by aspect ratio for a flat jacket channel (a one-sided heated wide channel is the likely jacket case), and any constant wall temperature value for a rectangle. A search result quoting a table copy lists 3.61, 4.12, 4.79, 5.33, 6.05, 6.49, 8.24 for aspect ratios 1, 2, 3, 4, 6, 8, infinity (https://engineersedge.com/heat_transfer/nusselt_number_13856.htm, 403 when opened, so not read); it names no source and is not recorded as a value. A design whose jacket reads Re below 2300 has only the square-duct value 3.610 recorded, so the code must refuse a laminar jacket with an aspect ratio other than 1 (grade C, secondary). **Status: formula known, primary not read; the square-duct value 3.610 and the circular values come from page summaries and are left out of defaults.** A laminar jacket (Re below 2300) is therefore refused by the code, or the plan finds a read source for the aspect ratio.

### 6.2 Air gap

**Romanazzi and Howey 2015 (item 6c).** P. Romanazzi and D. A. Howey, "Air-Gap Convection in a Switched Reluctance Machine", 2015 Tenth International Conference on Ecological Vehicles and Renewable Energies (EVER), University of Oxford, arXiv:1502.05902 (https://arxiv.org/abs/1502.05902). Read in full.

- **Correlation:** Nu = 0.181 Ta_m^0.207, "for 10^2 < Ta_m < 3 x 10^4", a least-squares fit of the CFD data (p. 6, conclusions and Fig. 10). CFD: unsteady LES in STAR-CCM+ v9.06, 8/6 SRM, smooth stator, periodic boundaries axially (infinitely long annulus, no end effects), stator at 60 degC and rotor at 35 degC. Dimensions (Table II, p. 5): stator inner radius 95.95 mm, rotor outer radius 95.00 mm, gap 0.95 mm, rotor pole height 33.5 mm, rotor pole arc 23 degrees, 6 rotor poles. Gap over radius is therefore 0.01.
- **Definitions (p. 2):** Nu = q g / (k (T_R - T_S)) = h g / k (Eq. 4), g the gap width, averaged over the whole internal annulus surface, k the mean of the values at the two wall temperatures. Ta_m = omega^2 R_m g^3 / nu^2 x 1/F_g (Eq. 1), R_m = b / ln((R_i + b)/R_i) with b = A / (2 pi R_i), F_g = (pi^4 / (1697 P)) (R_i + R_o) / (2 R_i) (Eq. 2, printed "1967" in both the PDF image and the LaTeX source), P = 0.0571 (1 - 0.652 g/R_i) + 0.00056 (1 - 0.652 g/R_i)^-1 (Eq. 3, printed "0652" in the first term in both the PDF image and the LaTeX source, and 0.652 in the second). **The symbol A in b = A / (2 pi R_i) is not defined in the text.** The arXiv LaTeX rendering (https://ar5iv.labs.arxiv.org/html/1502.05902) shows the same: F_g = pi^4 / (1967 P) x (R_i + R_o) / (2 R_i), P = 0.0571 (1 - 0652 g/R_i) + 0.00056 (1 - 0.652 g/R_i)^-1, and A never defined; the ORA record (https://ora.ox.ac.uk/objects/uuid:6995b9ea-1f80-4409-942a-e30145305bf2) gave no full text. The digits 1967 (against Taylor's 1697 quoted on p. 2) and 0652 are therefore in the source as printed and **stay unresolved**; A stays undefined. Ta_m cannot be evaluated as the paper defines it, and the code must not guess. The fit therefore cannot be coded yet; it is recorded as the cited CFD correlation. Bouafia's paper (the paper's ref. [21]) defines Ta_m and was not reached.
- **Scatter:** none stated as a number. Fig. 10 plots the CFD points beside the fit and the points lie close to it; this was looked at, not digitised, and no band is read from it. The paper says Nu never exceeded the smooth-cylinder correlation of Becker and Kaye ("Nu = 1 for Ta_m < Ta_c; Nu = 0.064 Ta_m^0.367 for Ta_c < Ta_m < 10^4; Nu = 0.205 Ta_m^0.241 for 10^4 < Ta_m < 10^6", p. 3, Ta_c = 1740 non-adiabatic, p. 2).
- **Below the fitted range:** the CFD heat transfer "for low value of Ta_m is below unity Nu" (p. 6), and the fit gives Nu 0.47 at Ta_m = 100. The conduction limit Nu = 1 belongs to the smooth Becker and Kaye case, so Nu = 1 is **not** a cited floor for the salient rotor. No cited correlation exists below Ta_m = 100 or above 3e4; the paper names 10 000 r/min (Ta_m about 1e5) as future work.
- **Grade B:** CFD, one 8/6 geometry, one gap ratio, smooth stator.

**Second cited air-gap route, Faiz 2009 (item 6c).** J. Faiz et al., IEEE Trans. Magn. 45(7), 2927-2934, 2009 (local PDF p. 4, journal p. 2930). Heat transfer from stator and windings to the air gap "is modeled by forced convection due to the rotation of the rotor" (p. 2). For the inner surfaces of the stator pole and slot wedge the paper treats the surface as a flat plate in an external flow, Eq. (6) as printed: Nu = h L / k = 0.664 Re^(1/2) Pr^(1/3), Re = L v_f / nu, L the length of the stator pole and slot wedge arcs, v_f the air velocity taken as the speed of the rotor tooth; the source given is Incropera and DeWitt 1990 (its [16], not read). No validity range or accuracy is printed. The paper reports h = 70 W/(m2 K) at 1000 r/min for its 8/6 (stator OD 125 mm, rotor OD 63 mm, gap 0.35 mm, pole arc 21 degrees, p. 5). Check by this file's arithmetic with air properties of Table III, v_f = omega x 31.5 mm = 3.30 m/s and L = 21 degrees at the 31.85 mm stator bore radius = 11.67 mm: h = 65.9, 65.5 and 65.2 W/(m2 K) with the 20, 40 and 60 degC columns, so the printed 70 is not reproduced to better than 7 % with these inputs (the film temperature and L used by Faiz are not stated). Grade C.

**Spread and floor at the same conditions (the controller's ruling for a band with no stated scatter).** Cited correlations: Romanazzi and Howey (cannot be evaluated until A is defined) and Faiz Eq. (6) (about 65 W/(m2 K) on the Faiz geometry above). The pure-conduction value k_air / g across the gap is 73.4, 77.4 and 81.4 W/(m2 K) for the same 0.35 mm gap with the 20, 40 and 60 degC conductivities of Table III. Note that Faiz Eq. (6) lies below that conduction value for these inputs, because it describes the pole and wedge surfaces and not a gap-spanning Nusselt number, and that the Romanazzi CFD itself gives Nu below 1 (h below k_air / g) for Ta_m near 100 (p. 6, the fit gives 0.47 at Ta_m = 100). So the "physical floor" k_air / g is not a floor in the cited CFD at low Ta_m. The band rule, "lowest of the cited correlations at the same conditions", is applied in section 7; the two correlations were not compared at one common geometry because Romanazzi cannot be evaluated.

### 6.3 Natural convection and end space (item 6d)

All three formulas below are printed in Faiz 2009 (local PDF pp. 3 and 4; journal pp. 2929 and 2930), which cites Markovic, Saunders and Perriard, "Determination of the thermal convection coefficient for a small electric motor", IEEE IAS 2006, pp. 58-61 ([17] there, not read) as their source. Grade C: a paper quoting another paper's correlations. The paper prints no Rayleigh range and no accuracy for any of them.

- **Horizontal cylinder, Eq. (1) with Eq. (2):** Nu = h D / k = {0.6 + 0.387 Ra_1^(1/6) / [1 + (0.559/Pr)^(9/16)]^(8/27)}^2, Ra_1 = g beta (T_s - T_a) D^3 / (nu alpha), D the outer diameter of the stator yoke, properties at the film temperature T_f = (T_s + T_a)/2, "obtained by a linear interpolation of the data in Table III" (p. 3). The same form is Churchill and Chu, Int. J. Heat Mass Transfer 18(9), 1049-1053, 1975, doi:10.1016/0017-9310(75)90222-7 (original not read; the `ht` documentation, a search result, gives Ra 1e-5 to 1e12 for it and is not used for a default).
- **Vertical plate, Eq. (3) and (4):** Ra_2 = g beta (T_s - T_a) H^3 / (nu alpha); Nu_2 = h H / k = {0.825 + 0.387 Ra_2^(1/6) / [1 + (0.492/Pr)^(9/16)]^(8/27)}^2 (p. 4). The circular end faces of diameter D are replaced by a square H x H of equal area, H = (sqrt(pi)/2) D = 0.886 D (Eq. 5).
- **Air properties, Faiz Table III "Air property [17]" (PDF p. 3):**

| T (degC) | k (W/(m degC)) | nu (1e-6 m2/s) | alpha (1e-6 m2/s) | Pr | beta (1e-3 1/degC) |
|---|---|---|---|---|---|
| 20 | 0.0257 | 15.11 | 23 | 0.713 | 3.43 |
| 40 | 0.0271 | 16.97 | 25.87 | 0.711 | 3.2 |
| 60 | 0.0285 | 18.90 | 28.81 | 0.709 | 3 |

  The table covers 20 to 60 degC. A film temperature outside that range has no cited property and the code must refuse it, or the plan must record a source beyond 60 degC; the end space of a hot machine may exceed it. Table II of the same paper gives air k = 0.0263 W/(m degC), specific heat 1007 J/(kg degC), density 1.16 kg/m3 (PDF p. 2).
- **A cited h for one motor** (Faiz 2009, pp. 4 and 5, 8/6 SRM, OD 125 mm): natural convection 5.2 W/(m2 K) over the frame and 5 W/(m2 K) over the lateral surfaces; forced 30 W/(m2 K) at 4 m/s over the frame; 70 W/(m2 K) at 1000 r/min over the inner stator pole and winding surfaces. These are results for that machine and are not carried to another; radiation is not included and Faiz notes it may matter (p. 5).
- **Second end-space route (open survey):** A. Boglietti, A. Cavagnino, D. Staton, M. Shanel, M. Mueller, C. Mejuto, "Evolution and Modern Approaches for Thermal Analysis of Electrical Machines", IEEE Trans. Ind. Electron. 56(3), 871-882, March 2009 (https://descargas.indielec.com/web/Thermal_Analysis_Approaches.pdf, read in full), Section VI, printed p. 879 (PDF p. 9). For totally enclosed machines the forced-convection coefficient between end winding and endcaps is h_C = 6.22 v (Eq. 9), v the air speed inside the endcap in m/s (the unit is not printed in the text read), or h = 41.4 + 6.22 v for combined natural and forced convection (Eq. 10); "other alternative relationships are also available [24], [29], [45], [49] and give similar results" (not read). Typical combined natural convection and radiation coefficient of the external frame: 12 to 14 W/(m2 degC) "for simple geometric shapes [49]" (same page); radiation coefficients 8.5 (copper to lamination), 6.9 (end winding to external cage), 5.7 (cage to ambient) W/(m2 degC) from the authors' ref. [46]. No stated accuracy; the survey says the parameters "may be difficult to find" and gives starting values. Grade C.

### 6.4 Oil spray and the other oil options

**End winding spray, measured h (item 6e).** Two measured sources, with rigs that differ by a factor of about five in h; neither carries over to the other.

1. F. Hoffmann, J. Bender, M. Parche, T. Wetzel, M. Doppelbauer (KIT), "Local Heat Transfer Coefficient Measurements on Shaft Spray Cooled End Windings" (6-page manuscript, venue not stated in the file; KIT record https://publikationen.bibliothek.kit.edu/1000163087). Four radial 1 mm holes in a rotating shaft spray the end winding (p. 3); a silicone model end winding of inner diameter 115 mm on a stator of inner diameter 110 mm, 36 slots; **model fluid** water-glycerol (about 11 % water) at 54 to 68 degC, chosen to match the Prandtl number of transmission oils at 60 to 90 degC (p. 2 and 3); flow per hole 0.5 to 0.7 l/min (system 5.6 l/min over eight holes); speed -10 000 to 10 000 r/min. Read from Fig. 4 and Fig. 5 (p. 4), about, off the sump: **3500 to 4800 W/(m2 K)**, with a sump at the 180 degree position **1100 to 2700 W/(m2 K)**; the speed has a minor influence. Model, p. 5, Eq. 9: Nu = ratio_spray x 2.29 x Re^0.28 x Pr^(1/3), ratio_spray = asin(b_MEL / d_in,stator) x num_holes / pi = 0.14 for this rig (Eq. 5), Re = v_F d_0 rho / nu with v_F = sqrt((V / (pi d_0^2 / 4))^2 + (omega r_shaft)^2) (Eq. 7 and 8), d_0 = 1 mm. The mean absolute percentage error is 10.8 % and 93 % of the points are inside +-25 % (p. 6, Fig. 8); the fit leaves out points in a sump. The paper restricts the correlation to the investigated parameters (spray distance, axial offset and stator inner diameter were not varied). **The length scale of Nu is not stated in the text**; d_0 fits the magnitudes of Fig. 8 but that is an inference, so the code takes h from the measured range and not from Eq. 9. Properties of the model fluid are not tabulated in the text read. Grade B.
2. P. Shams Ghahfarokhi, A. Podgornovs, A. J. Marques Cardoso, P. Rasilo, "Assessment of nozzle performance in high-viscosity oil spray system for rectangular copper conductors", Int. J. Thermal Sciences 204, 109244, 2024 (open access; https://homepages.tuni.fi/paavo.rasilo/pubs/ShamsGhahfarokhi2024.pdf). A heated rectangular hairpin conductor sprayed by seven nozzle types, a fixed distance, oil of kinematic viscosity 1e-5 m2/s at 40 degC and 2.7e-6 m2/s at 100 degC and density 0.84 at 15 degC (Table 1, p. 3; the unit is misprinted kg/m3), nozzle pressure 1 to 4 bar, flow 0.65 to 1.5 l/min (Fig. 4 and 5, pp. 5 and 6). Read from Fig. 5 (p. 6): **about 190 to 910 W/(m2 K)** across all nozzles and operating points (190 for a wide full cone at 1 bar, 910 for the 90 degree flat fan at 4 bar), the hollow cone nozzle flat near 270 to 290. Measurement uncertainty of h +-6.08 % (p. 5). The oil inlet temperature is not given in the text read. Grade B.

A CFD paper (UKHTC 2024 paper 73) gives 530 W/(m2 K) for a 2 mm radial nozzle at 75 kg/min; it is a simulation and is not used.

**Shaft oil cooling to the rotor (item 6f): not found.** Neither paper above is about oil to a rotor through the shaft bore, and no other source was read. The code refuses this option.

**Slot oil channel (item 6g): not found.** Marquez-Fernandez 2018 (p. 4) says the coolant flow model uses Darcy-Weisbach resistances and takes the convection coefficients from the flow model, and prints no h and no Nusselt correlation. Its coolant is water (6 to 9 l/min, Section V, p. 4 and 5). A water-glycol slot channel is a duct problem and uses item 6a and 6b; an oil slot channel has no property data (see 6.7). The code refuses a slot-oil option with oil.

### 6.5 Stator-housing contact (item 6h)

Source: Boglietti, Cavagnino, Staton, Shanel, Mueller, Mejuto, IEEE Trans. Ind. Electron. 56(3), 871-882, 2009, Section VI-E "Interface gap between lamination and external frame", printed pp. 879 and 880 (PDF pages 9 and 10; the same open survey as in 6.3). As printed: the gap "is due to imperfections in the touching surfaces, and it is a complex function of material hardness, interface pressure, smoothness of the surfaces, and air pressure"; "for industrial induction motors, interface gap values between 0.01 and 0.08 mm have been found"; the value cannot be computed because the stator core assembly and the core-into-frame insertion process affect it; "a value of 0.03 mm can be considered a reasonable value to be used as a default at the start of the design process"; sensitivity analysis "with the interface gap varied between 0.01 and 0.08 mm"; "in highly rated machines, such as those with housing water jackets, it can be significant". The fit type is an equivalent air gap (the thermal resistance of an air layer of that thickness); the survey does not print the conversion or a table. The primary the survey rests on, Staton, Boglietti and Cavagnino, IEEE Trans. Energy Convers. 20(3), 620-628, 2005 (cited as [15] in Faiz 2009), was not reachable (403 at iris.polito.it; empty page at scispace; 403 at core.ac.uk); search summaries of its table (0.042, 0.076 and 0.077 mm for three totally enclosed induction motors) are not an opened document and are not recorded as values. Simpson, Wrobel, Booker and Mellor, IET PEMD 2016, doi:10.1049/cp.2016.0129, has no full text found and its abstract states no gap. Faiz 2009 gives no contact value. **Recorded:** nominal 0.03 mm, range 0.01 to 0.08 mm, grade C (a survey by the authors of the primary, industrial induction motors, frame material not stated, not an SRM). The survey says the gap depends on the frame material and the insertion process, so for an aluminium housing in a water jacket the range is an assumption of transfer from induction motors, which the plan should say in the UI.

### 6.6 Slot liner, resin, housing and winding (items 6i to 6k, 6m)

| Item | Value | Source and page | Grade |
|---|---|---|---|
| Slot liner | 0.076 W/(m K), density 2150 kg/m3, specific heat 1172 J/(kg K) | Faiz 2009 Table II (image, PDF p. 2), "thermal parameters [3], [16]", single value, no range | C |
| Slot wedge | 0.29 W/(m K) | Faiz 2009 Table II | C |
| Nomex 410 | 0.103 (0.05 mm, density 0.72 g/cc), 0.114 (0.08 mm, 0.81), 0.123 (0.13 mm, 0.88), 0.143 (0.18 mm, 0.95), 0.139 (0.25 mm, 0.96), 0.149 (0.38 mm, 1.02), 0.157 (0.51 mm, 1.06), 0.175 W/(m K) (0.76 mm, 1.08); all at 150 degC, ASTM E1530; typical values; Figure 9 gives the 0.25 mm paper against temperature (not digitised) | DuPont Nomex 410 technical data sheet K-20612-3 (06/20), Table IV and the text above it, PDF p. 5, read from the copy at https://marianinc.com/wp-content/uploads/2024/09/Nomex_410.pdf; DuPont's text says thinner grades have slightly lower conductivity and the system construction may change the overall value | B (manufacturer data sheet) |
| Impregnation epoxy | "ranging from 0.6 to 1 W/(m K)", actual value not known, depends on fillers | Marquez-Fernandez 2018, PDF p. 8 | B |
| Winding, equivalent (random wound) | 0.6 to 0.9 W/(m K), used 0.83 | Faiz 2009 pp. 3 (text), citing [3], [14] | C |
| Copper along the wire | 300 W/(m K) used by the authors | Marquez-Fernandez 2018, PDF p. 3 | B (their model input) |
| Frame, aluminium | 177 W/(m K), 875 J/(kg K), 2770 kg/m3 | Faiz 2009 Table II | C |
| Stator lamination | 20 W/(m K), 438 J/(kg K), 7650 kg/m3 | Faiz 2009 Table II (10JNEX900: 18.6 in section 1) | C |

The 6061-T6 value of 167 W/(m K) and the 6061-O and -T8 values from the MatWeb search result were deleted: no document was opened (connection refused). A380 die casting: search results run from 92 to 130 W/(m K) and no data sheet was reached, so no value is recorded for it. The housing therefore carries the single read value 177 W/(m K) (Faiz 2009 Table II, no alloy named). The Nomex table (the SynFlex page quoted earlier carries the same numbers) has no value at 0.30 and 0.61 mm.

### 6.7 Coolants (item 6l)

**50/50 water and ethylene glycol.** Source: MEGlobal, *Ethylene Glycol Product Guide* (https://www.meglobal.biz/wp-content/uploads/2019/01/Monoethylene-Glycol-MEG-Technical-Product-Brochure-PDF.pdf, 9/12/13 edition), Figures 7, 8, 9 and 17 with their curve-fit tables on printed pages 18, 19, 20 and 28 (PDF pages 19, 20, 21, 29). Values for 50 weight percent glycol, computed from the printed fits:

| Temperature | Density kg/m3 | Specific heat J/(kg K) | Conductivity W/(m K) | Dynamic viscosity mPa s |
|---|---|---|---|---|
| 37.8 degC (100 F) | 1054 | - | - | 2.20 |
| 40 degC | - | 3534 | 0.417 | - |
| 65 degC | - | 3611 | 0.414 | - |
| 65.6 degC (150 F) | 1036 | - | - | 1.18 |
| 93.3 degC (200 F) | 1016 | - | - | 0.739 |
| 100 degC | - | 3718 | 0.406 | - |

How these were computed: viscosity log10(cP) = A - B/(x + C) with x = weight percent, one A, B, C row per temperature in degF (150 F row: A -3.619555, B 1368.620, C -420.761); specific heat (Btu/(lb degF), x 4186.8) = A + B T + C T^2 with T in degC (50 % row: 0.81485, 7.3219e-4, 0); conductivity (Btu/(h ft degF), x 1.7307) = A + B T + C T^2 (50 % row: 0.23951, 8.9758e-5, -1.3975e-6); specific gravity (T/60 F) = A + B x + C x^2 with the A, B, C row per temperature in degF (150 F row: 0.98017, 1.2599e-3, -2.3334e-6), density taken as SG x 999.0 kg/m3 (water at 60 F). That 999.0 is this file's assumption, not the guide's. The guide's tabulated temperatures are degF rows for viscosity and density, so 65 degC (149 F) is read at 150 F (65.6 degC); no interpolation was made. A second source (Engineering ToolBox) gave 1067 kg/m3 at 40 degC against 1054 here (1.2 % apart, its table alignment inferred), unresolved and not used. Grade B (manufacturer product guide).

**Automatic transmission fluid and motor oil (item 6l): density and viscosity found for single fluids, specific heat and conductivity not found.**

| Fluid | Kinematic viscosity | Density | Source |
|---|---|---|---|
| High-viscosity spray oil | 1.0e-5 m2/s at 40 degC, 2.7e-6 at 100 degC | 0.84 at 15 degC (unit printed as kg/m3) | Shams Ghahfarokhi et al. 2024, Table 1, PDF p. 3 |
| Dexron III (Motul) | 33.4 mm2/s at 40 degC, 7.2 at 100 degC | 0.846 at 20 degC | search-result summary of a spec sheet, not opened |
| Dexron VI (77 Lubricants) | 27.2 mm2/s at 40 degC, 5.7 at 100 degC | 844 kg/m3 at 15 degC | same |
| ATF III table (Anton Paar wiki, 0 to 100 degC in 10 degC steps) | 35.55 at 40 degC, 7.77 at 100 degC | 0.8527 and 0.8140 g/cm3 | same |

Specific heat and thermal conductivity of any ATF or motor oil: **not found**. Viscosity at 65 degC: no tabulated source read. Without them the Prandtl number of an oil cannot be computed, so no oil-coolant duct correlation can be coded. An oil spray h comes from the measured ranges in 6.4, which need no oil properties, and an oil coolant at the jacket or in a slot is refused.

**Shell Diala S4 ZX-I (the owner's spray oil, decided 2026-11-10).** A GTL transformer oil (IEC 60296 Type A).

- Data sheet: Shell, *Technical Data Sheet Shell Diala S4 ZX-I*, v4.3 (06.10.2021), page 2, typical values (https://motex.bg/PDS/PDS-Shell-Diala-S4-ZX-I.pdf, opened): density **805 kg/m3 at 20 degC** (ISO 3675), kinematic viscosity 9.6 mm2/s at 40 degC and 382 at -30 degC (ISO 3104), closed-cup flash point 191 degC (ISO 2719), pour point -42 degC, breakdown voltage 70 kV (IEC 60156), no corrosive sulphur. No specific heat, conductivity or expansion. Grade B.
- Specific heat: C. S. Cragoe, *Thermal Properties of Petroleum Products*, Bureau of Standards Miscellaneous Publication 97, 1929, doi:10.6028/NBS.MP.97 (https://nvlpubs.nist.gov/nistpubs/Legacy/MP/nbsmiscellaneouspub97.pdf, opened), p. 26, Eq. 5: **c = (0.388 + 0.00045 t) / sqrt(d)** cal/(g degC), t in degF, d the specific gravity at 60/60 F. Based on over 100 measurements on 30 oils, d 0.75 to 0.96, 32 to 400 F; within 2 % on average and about 4 % at most; oils from paraffin-base crudes read about 2 % above the equation (p. 26). Checked against the worked example on p. 28 (30 API, d 0.8762, 100 F: 0.463). For Diala d = 805 / 999.0 = 0.806 (the 20 degC density stands in for 60 F; the true d is a few tenths of a percent higher, so cp reads under 0.2 % high). The unfavourable end of the `cooling_h` row takes cp minus 4 %. A GTL oil is paraffinic, so the equation itself errs low. Grade B.
- Conductivity: Cragoe p. 24, Eq. 4: K = (0.813 / d) [1 - 0.0003 (t - 32)] Btu in/(h ft2 degF), about 10 % accuracy (checked against Table 10, d 1.0 at 0 F: 0.82). Not coded: end spray takes h from the measured range in 6.4 and needs only rho cp; a duct with oil also needs a viscosity curve and, at oil Reynolds numbers, a laminar Nu, neither of which is read.
- Expansion: **not found** (no data sheet or opened source for this oil). The code uses the 20 degC density at every temperature; at a 60 degC inlet a petroleum oil is a few percent lighter, so the oil temperature rise reads a few percent low. The note on every spray result says so.
- Fit to the spray rig: Shams Ghahfarokhi et al. 2024 (6.4) sprayed an oil of 1.0e-5 m2/s at 40 degC, close to Diala's 9.6e-6, so its h band is the matching one (`nozzle_hairpin`, the default).

### 6.8 Cross-wire winding conductivity (item 6m)

Marquez-Fernandez 2018, PDF p. 7 (Eq. 5) and p. 8 (Eq. 6 and the text after it). Symbols: lambda_i conductivity, theta_i volume fraction of material i, sub-index 1 copper and 2 the potting epoxy, xi a parameter that depends on the fill factor ("for K_f = 0.37 equals 0.324"), after Idoughi et al., IEEE Trans. Magn. 47(12), 4822-4826, 2011 (their ref. [18]; not read) and Milton, J. Appl. Phys. 52, 5294-5304, 1981 ([19]; not read).

- **Hashin-Shtrikman, Eq. (5) as printed:** lambda_HS = lambda_2 ((1 + theta_1) lambda_1 + (1 - theta_2) lambda_2) / ((1 - theta_1) lambda_1 + (1 + theta_2) lambda_2).
- Eq. (5) is coded as printed. The printed form differs from the standard 2D Hashin-Shtrikman lower bound: with copper 300 and resin 1 W/(m K) it gives 0.993 instead of 1.0 at fill 0 and is 0.2 % below the standard form at fill 0.37 (the safe side); python -I arithmetic.
- **Milton, Eq. (6) as printed:** lambda_M = lambda_2 ((theta_1 lambda_1 + theta_2 lambda_2 + lambda_1)(lambda_1 + lambda_2) - theta_1 xi (lambda_1 - lambda_2)^2) / ((theta_2 lambda_1 + theta_1 lambda_2 + lambda_2)(lambda_1 + lambda_2) - theta_1 xi (lambda_1 - lambda_2)^2).
- **Copper conductivity** used by the authors in the winding model: kappa_wl = 300 W/(m K) along the wire (p. 3). The conductivity they put into Eq. (6) is not stated.
- **xi as a function of fill factor: not found** (it is in Idoughi 2011, unreachable). Only xi = 0.324 at 0.37 is on record. For test motorette B (fill 0.47) the paper gives no xi.
- Fig. 17 (p. 8) plots Eq. (5) and (6) at fill 0.37 for potting conductivities; it was not digitised.
- The paper itself says (p. 8 and p. 9) that the Milton value "may be on the low side" for the litz coil, that preliminary measurements on infiltrated litz samples suggest higher values, and that the twist adds a third dimension.

**Computed for this file (python -I arithmetic, nothing adjusted):**

| Fill | Resin W/(m K) | HS, Eq. (5) | Milton, Eq. (6), xi 0.324, copper 300 (391) |
|---|---|---|---|
| 0.37 | 1.0 | 2.158 (2.162) | 2.430 (2.434) |
| 0.37 | 0.6 | 1.299 (1.300) | 1.463 (1.465) |
| 0.47 | 1.0 | 2.750 (2.756) | 3.439 (3.450) |
| 0.47 | 0.6 | 1.656 (1.658) | 2.075 (2.079) |

The HS value is 11 % below Milton at fill 0.37 and 20 % below at 0.47, with the same resin. The V3 hand check of these against the printed 2.41 and 3.11 is in section 8.

### 6.9 Lamination conductivity scatter (item 6n)

Values on record: 18.6 W/(m K), direction not stated (Ou et al. 2021 Table I, section 1; grade C) and 20 W/(m K) (Faiz 2009 Table II; grade C; a different steel). No source read states a scatter. A search result describes NREL measurements of M19 and other grades at 20 to 23 W/(m K) in the bulk and 0.7 to 2.1 W/(m K) effective through-stack; those papers were not reachable and are not recorded as values. **Rule used (the plan's call):** with no cited scatter the unfavourable end takes the grade-C allowance of the project, `srmapp.losses.LOSS_GRADE_ALLOWANCE["C"]` = 0.25 (provisional there as well): 18.6 x (1 - 0.25) = **13.95 W/(m K)**. It is a rule applied to a grade-C value, not a measurement; it holds until a grade A or B value exists.

## 7. Bands

One row for each budget row of spec §7 that needs a band. "Nominal" is what the model uses. "Unfavourable" is the end the worst-case stack uses. A row marked **no band** has no cited unfavourable end and the code must either refuse the option or take the value from the owner; it never takes a number from this table that is not written here.

| Row | Nominal | Unfavourable end | Where it comes from | Status |
|---|---|---|---|---|
| `cross_wire` | Milton, Eq. (6), xi 0.324, at fill 0.37 (xi at other fills is **not found**, so for any other fill the nominal falls back to the HS value) | the HS value of Eq. (5) at the same fill and resin, 11 % below Milton at fill 0.37 and 20 % below at 0.47 (6.8). The band is widened on the favourable side to cover the measured-agreement values 3.0 (fill 0.37) and 3.85 W/(m K) (fill 0.47) of Marquez-Fernandez 2018 (24 % above the Milton values 2.41 and 3.11). The HS-to-Milton band alone did not cover them, since both lie above Milton; the wider end only widens the band and sets nothing in the model | 6.8 and 8; spec §8 V3 "revise the band, not the measured values" | band found for fill 0.37 (HS to 3.0 against a Milton nominal of 2.41 to 2.43), HS-only for other fills |
| `liner` | Nomex 410 by thickness from DuPont's Table IV (0.103 to 0.175 W/(m K) at 150 degC) | 0.076 W/(m K) (Faiz 2009 Table II, the lowest value read) | 6.6 | band found; the Nomex values are grade B, the 0.076 grade C with no stated range |
| `impregnation` (resin, in the same spec row as the liner) | 1.0 W/(m K), the value the authors simulated (Milton 2.41 at fill 0.37) | 0.6 W/(m K) | Marquez-Fernandez 2018 p. 8 | band found, grade B |
| `contact` | 0.03 mm equivalent air gap | 0.08 mm | 6.5; Boglietti et al. 2009 Sec. VI-E, a survey on industrial induction motors, frame material not stated | band found, grade C, transfer to an SRM in an aluminium jacket assumed |
| `air_gap` | Romanazzi and Howey, Nu = 0.181 Ta_m^0.207, 1e2 < Ta_m < 3e4 (not codable until A is defined) | by the controller's rule: the lowest of the cited correlations at the same conditions, among Romanazzi and Howey and Faiz Eq. (6) (about 65 W/(m2 K) at the Faiz geometry); the pure-conduction value k_air / g is a second candidate floor but the Romanazzi CFD sits below it near Ta_m = 100 | 6.2 | **band defined by rule, not by a stated scatter**; Romanazzi cannot be evaluated, so only the Faiz route has a number; the plan must choose |
| `cooling_h` jacket (water-glycol) | Gnielinski (6.1) with the 50 wt % properties at 65 degC; Re 1e4 to 1e6 (the friction factor of Eq. 7 starts at 1e4); a laminar or transition jacket is refused (6.1) | h at minus 10 % (Shah and Sekulic via Jacimovic et al.) | 6.1, 6.7 | band found, grade C |
| `cooling_h` end space | Churchill and Chu on the external faces (Faiz Eq. 1 to 5, Table III, 20 to 60 degC only); inside the endcaps h_C = 6.22 v of Boglietti et al. Eq. 9 needs an air speed that no source gives for a given machine | the lowest of the cited routes at the same conditions: Churchill and Chu, Boglietti Eq. 9 and Eq. 10, and the 12 to 14 W/(m2 degC) external figure, per the controller's rule | 6.3 | **band defined by rule**; no stated accuracy for any route; the air speed v is an input nobody cites |
| `cooling_h` end spray | the measured range of the chosen rig: nozzle spray on a hairpin 190 to 910 W/(m2 K), or shaft spray 3500 to 4800 W/(m2 K) | the low end of that range, or for the shaft spray inside a sump 1100 W/(m2 K); the Hoffmann model adds minus 25 % | 6.4; neither rig is the owner's geometry | measured ranges found, two disjoint rigs, selection is the plan's |
| `cooling_h` shaft oil | none | none | 6.4 | **not found**, option refused |
| `cooling_h` slot oil | water-glycol: as the jacket row; oil: none | water-glycol: minus 10 % | 6.4 | oil **not found**, option refused with oil |
| `lamination_k` | 18.6 W/(m K) | 13.95 W/(m K) = 18.6 x (1 - 0.25), the grade-C allowance of `LOSS_GRADE_ALLOWANCE["C"]` | the plan's rule applied to Ou et al. Table I (6.9) | rule, grade C |

Rows of spec §7 that this task does not source: iron loss, EM torque, thermal mesh, end-winding model (they come from R3, R4 and the V4 and V5 gates).

### Placeholders (owner placeholders, no source)

These are the default cooling setup of spec §2 decision 5, labelled "placeholder cooling" in the UI. They are not from any source; the owner sets them. The inlet temperature and the insulation class are fixed by the spec.

| Placeholder | Value |
|---|---|
| Coolant | 50/50 water and ethylene glycol |
| Inlet temperature | 65 degC (spec decision 5) |
| Insulation class | H, 180 degC, hot-spot limit 160 degC (spec decision 5) |
| Jacket channel height | 4 mm |
| Jacket channel width | 20 mm |
| Number of passes | 4 |
| Flow | 9 L/min = 1.5e-4 m3/s |
| Housing thickness | 8 mm |
| Ambient | 40 degC (owner placeholder) |
| Natural-convection surface temperature | 80 degC, i.e. 2 x 60 - ambient (an assumption, not cited; sets the end-frame and end-face h at the 60 degC air film) |

Check of the flow regime this gives (arithmetic only, with the 65 degC properties interpolated from section 6.7): hydraulic diameter 2 h w / (h + w) = 6.67 mm, section 80 mm2, mean speed 1.875 m/s, Re about 1.1e4, inside the Gnielinski range (Re above 1e4). The flow was raised from 8 L/min (Re about 9800, below 1e4, so refused) to 9 L/min so the default jacket is in range.

## 8. V3 record: the winding model against Marquez-Fernandez 2018

Source: F. J. Marquez-Fernandez, J. H. J. Potgieter, A. G. Fraser, M. D. McCulloch, "Experimental validation of a thermal model for high speed switched reluctance machines for traction applications", IEEE Trans. Ind. Appl. 54(4), 2018, pp. 3235-3244 (accepted manuscript, 10 PDF pages), doi:10.1109/TIA.2018.2817182. Page numbers are the manuscript's PDF pages.

| Quantity | Value | Where |
|---|---|---|
| Test motorette A fill factor (copper volume ratio) | 0.37 | Table II (p. 2), Section V.A (p. 4) |
| Test motorette B fill factor | 0.47 ("27 % higher") | Table II, Section V.B (p. 5), p. 9 |
| Winding | 12 turns, litz: set A 120 threads of 0.25 mm, set B 174 threads of 0.236 mm | Table II (p. 2) |
| Test current | DC 150, 180, 200 A (A: 25.5, 30.5, 34.0 A/mm2; B: 19.7, 23.7, 26.3 A/mm2); flow 6 to 7 l/min (A), 8 to 9 l/min (B); coolant water | pp. 4 and 5 |
| Epoxy potting conductivity | "ranging from 0.6 to 1 W/(m K)", not known for certain | p. 8 |
| Milton xi at fill 0.37 | 0.324 (xi at 0.47 not given) | p. 8, text after Eq. (6) |
| Winding conductivity along the wire | 300 W/(m K) | p. 3 |
| Milton across the wires, fill 0.37, resin about 1 W/(m K) | **2.41 W/(m K)**, used in the simulation of Fig. 16 | p. 8 |
| Same, simulated again for better agreement | **3.0 W/(m K)** (Fig. 16, bottom plot) | p. 8 |
| Milton across the wires, fill 0.47 | **3.11 W/(m K)** | p. 9 |
| Same, chosen for better agreement | **3.85 W/(m K)** (Fig. 19, bottom plot) | p. 9 |
| Stator pole conductivity | 17 W/(m K) in all directions (the soft magnetic composite of that machine) | p. 3 |
| Result | simulated temperatures higher than measured in all cases; "current densities above 26 A/mm2 (200 A) can be sustained continuously with a temperature difference of less than 65 degC to the coolant in the hottest point of the winding" | p. 9 (conclusions) |

The measured temperatures are from thermistors glued on the outer wall of the impregnated coil, and the authors say the simulated values are for the centre of the litz bundle (p. 7); a thermistor sits between turns 2 and 3, found when a motorette was cut open (p. 8 and 9). Plastic spacers stop the first turns from being cooled (p. 8). The thermal mass of the stainless case and the insulation is not in the simulation (p. 7).

**Hand check of Eq. (6) against 2.41 and 3.11** (copper 300 W/(m K), the value the paper names for the winding model; resin 1 W/(m K); xi 0.324; run with `python -I`):

| Fill | Eq. (6) result | Printed | Difference |
|---|---|---|---|
| 0.37 | 2.430 W/(m K) (2.434 with copper 391) | 2.41 | +0.8 % (+1.0 %) |
| 0.47 | 3.439 W/(m K) (3.450 with copper 391) | 3.11 | +10.6 % (+10.9 %) |

Result: the formula **reproduces 2.41 to within 1 %** (the printed figure is rounded and says "approximately 1 W/(m K)" for the resin, so this agrees within the stated precision) and **does not reproduce 3.11** with xi = 0.324, a value the paper gives for fill 0.37 only. Solving for xi on this formula gives 0.195 for 3.11 at fill 0.47 and 0.304 for 2.41 at 0.37; these are derived here and are not in the paper. Nothing was changed to make it match. The consequence is that the one fill dependence the code would need, xi(K_f), is the unfound item of section 6.8: until Idoughi 2011 is read, Milton is evaluated at 0.37 only and any other fill uses the HS value.

V3's 0.47 point is **not reproduced**: the paper gives xi for fill 0.37 only, and with xi = 0.324 the formula gives 3.44 against the printed 3.11. This is recorded and nothing is changed: the model value, the printed value and the better-fit value stay as they are, and the band of section 7 is widened instead (spec §8 V3).

The measured-agreement values are **24 % above** the Milton ones (3.0 / 2.41 = 1.245; 3.85 / 3.11 = 1.238 using the printed 3.11). The paper does not state the agreement as a number; it says only that the higher value gives "a better agreement" (pp. 8 and 9). So V3 as designed in spec §8 has: model input 2.41 or 3.11 (3.44 by this file's arithmetic for fill 0.47), and a better-fit value about 24 % higher, from one coil type each, with no temperature error reported as a number. A gate threshold must be set from the plan; the paper gives none.
