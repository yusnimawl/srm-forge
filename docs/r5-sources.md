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
| 6a | Gnielinski turbulent duct Nu, friction factor, range, scatter | Incropera 7th ed. Sec. 8.5 Eq. 8.62 p. 514 and Petukhov f, as quoted by the Bobolea `htcie` page; Gnielinski 1976 not read | C (secondary quoting a textbook) | formula and range found; the 10 % scatter is second-hand and marked uncertain there |
| 6b | Laminar fully developed Nu, rectangular duct | `ht` docstring citing Shah and London 1978 (square, constant heat flux, 3.610 only) | C | square value only; other aspect ratios and constant wall temperature **not found** from a read source |
| 6c | Air-gap Nu for a salient rotor, 8/6 | Romanazzi and Howey 2015, EVER, pp. 2 and 6 (arXiv 1502.05902) | B (CFD least-squares fit, one geometry) | formula, range and Ta_m definition found; no scatter stated; the area A in Ta_m is **not defined** in the text |
| 6d | Natural convection, horizontal cylinder and vertical plate | Churchill and Chu 1975 (two papers) via the `ht` documentation | C | formulas and Ra range found; accuracy **not found**; Faiz 2009 gives its own h for one motor |
| 6e | Oil spray on end windings, h | Hoffmann et al. (KIT, shaft spray, model fluid); Shams Ghahfarokhi et al. 2024 (nozzles, one hairpin conductor) | B (measured, single rigs) | two measured h ranges found, 190 to 910 and 1100 to 4800 W/(m2 K), not transferable between rigs |
| 6f | Shaft oil cooling to the rotor, h | none | - | **not found** |
| 6g | Slot oil channel, h | Marquez-Fernandez 2018 prints no h | - | **not found**; water in a duct is covered by 6a |
| 6h | Stator to housing contact, equivalent gap | Staton, Boglietti, Cavagnino 2005 (not reachable, 403) | - | **not found** from a read source |
| 6i | Slot liner conductivity | Faiz 2009 Table II p. 2; SynFlex Nomex 410 table | C | 0.076 and 0.103 to 0.175 W/(m K) |
| 6j | Impregnation resin conductivity | Marquez-Fernandez 2018 p. 8 | B | 0.6 to 1 W/(m K) |
| 6k | Aluminium housing alloy | MatWeb ASM data sheet 6061-T6 (via search result); Faiz 2009 Table II | C | 167 and 177 W/(m K) |
| 6l | Coolants | MEGlobal Ethylene Glycol Product Guide pp. 18 to 20 and 28 (50 wt % glycol, 40 to 100 degC); ATF | B (glycol) / - | glycol found; ATF cp and conductivity **not found** |
| 6m | Cross-wire conductivity (Milton, Hashin-Shtrikman) | Marquez-Fernandez 2018 Eq. (5) and (6), pp. 7 and 8 | B | formulas found; xi found for fill 0.37 only |
| 6n | Lamination conductivity scatter | none read | - | **not found**; 12 W/(m K) is the plan's call, not a sourced value |
| 7 | Band for every budget row that needs one | sections 6 and 7 | - | section 7 |
| 8 | V3 record (Marquez-Fernandez 2018) | pp. 2, 3, 8 and 9 | B | section 8; hand check of Milton done, it does not reproduce 3.11 |

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

Read on 2026-11-09. Local PDFs (IEEE copyright, git-ignored, never committed): Marquez-Fernandez 2018 and Faiz 2009, read with PyMuPDF from a scratch directory. Open PDFs (Romanazzi and Howey 2015, Hoffmann et al., Shams Ghahfarokhi et al. 2024, the MEGlobal guide) were downloaded to scratch directories and read the same way. Reached only as a web search result or a page summary, not as a document: Churchill and Chu (via the `ht` documentation), Gnielinski (via the Bobolea `htcie` page and the Jacimovic et al. 2026 paper), the Nomex table (SynFlex page), 6061-T6 (MatWeb ASM data sheet, search result only). Not reachable (403, bot block or connection refused): Staton, Boglietti and Cavagnino 2005 (iris.polito.it, scispace, core.ac.uk), the NREL lamination papers, the Idoughi et al. 2011 paper (HAL), Incropera and Gnielinski 1976 themselves. Where a value comes from a search-result summary and not from an opened document, the entry says so. Page numbers are PDF pages of the file read unless "printed" is written.

### 6.1 Forced convection in a duct

**Gnielinski, turbulent (item 6a).** Nu = (f/8)(Re - 1000) Pr / (1 + 12.7 sqrt(f/8) (Pr^(2/3) - 1)), with f = (0.790 ln Re - 1.64)^-2, the Petukhov smooth-pipe friction factor. Read on the Bobolea `htcie` page (https://alinbobolea.github.io/docs/htcie/correlations/internal.html), which gives: Re 3000 to 5e6, Pr 0.5 to 2000, L/D at least 10, and cites Gnielinski, Int. Chem. Eng. 16(2), 359-368, 1976, and Incropera et al. 7th ed. Sec. 8.5 Eq. 8.62 p. 514 (f: Eq. 8.21). The `ht` documentation (https://ht.readthedocs.io/en/latest/_modules/ht/conv_internal.html, `turbulent_Gnielinski`, citing Gnielinski 1976 and Rohsenow, Hartnett and Cho 1998) gives Pr 0.5 to 2000 and Re 2300 to 5e6 and no error figure. Jacimovic et al., FME Transactions 54(3), 391-401, 2026, p. 393, say the author himself gave Re 2300 to 1e6 and Pr 0.5 to 500 in one paper and Re 4000 to 1e6 in another, that another source recommends 2300 to 5e6, that a further source advises against the critical range Re 2000 to 4000, and that the overall accuracy is about 10 %. The 10 % on the `htcie` page is marked UNCERTAIN there (taken from Cengel and Ghajar, 5th ed., Sec. 8-5; the 1976 paper was not checked). **Recorded for the code:** the formula above; validity Re 3000 to 5e6 (the narrowest of the stated lower bounds that is also Incropera's), Pr 0.5 to 2000; scatter about 10 %, grade C, second-hand. Outside Re 3000 to 5e6 no cited correlation is recorded (see the laminar entry for Re below 2300; 2300 to 3000 is not covered). The viscosity-ratio correction for a wall at another temperature than the bulk is not recorded; the code uses bulk properties and the band covers it.

**Laminar, fully developed (item 6b).** Found: circular tube Nu 3.66 (constant wall temperature) and 4.36 (constant heat flux) on the `htcie` page, which cites Shah and London 1978 (*Laminar Flow Forced Convection in Ducts*, Academic Press) without a page. For a rectangular duct, the `ht` documentation (`Nu_laminar_rectangular_Shan_London`, citing the same book and Shah and London 1971 Table 42) says the model assumes constant wall heat flux on all sides and that a square duct gives Nu 3.610224. **Not found:** Nu by aspect ratio for a flat jacket channel (a one-sided heated wide channel is the likely jacket case), and any constant wall temperature value for a rectangle. A search result quoting a table copy lists 3.61, 4.12, 4.79, 5.33, 6.05, 6.49, 8.24 for aspect ratios 1, 2, 3, 4, 6, 8, infinity (https://engineersedge.com/heat_transfer/nusselt_number_13856.htm, 403 when opened, so not read); it names no source and is not recorded as a value. A design whose jacket reads Re below 2300 has only the square-duct value 3.610 recorded, so the code must refuse a laminar jacket with an aspect ratio other than 1 (grade C, secondary).

### 6.2 Air gap

**Romanazzi and Howey 2015 (item 6c).** P. Romanazzi and D. A. Howey, "Air-Gap Convection in a Switched Reluctance Machine", 2015 Tenth International Conference on Ecological Vehicles and Renewable Energies (EVER), University of Oxford, arXiv:1502.05902 (https://arxiv.org/abs/1502.05902). Read in full.

- **Correlation:** Nu = 0.181 Ta_m^0.207, "for 10^2 < Ta_m < 3 x 10^4", a least-squares fit of the CFD data (p. 6, conclusions and Fig. 10). CFD: unsteady LES in STAR-CCM+ v9.06, 8/6 SRM, smooth stator, periodic boundaries axially (infinitely long annulus, no end effects), stator at 60 degC and rotor at 35 degC. Dimensions (Table II, p. 5): stator inner radius 95.95 mm, rotor outer radius 95.00 mm, gap 0.95 mm, rotor pole height 33.5 mm, rotor pole arc 23 degrees, 6 rotor poles. Gap over radius is therefore 0.01.
- **Definitions (p. 2):** Nu = q g / (k (T_R - T_S)) = h g / k (Eq. 4), g the gap width, averaged over the whole internal annulus surface, k the mean of the values at the two wall temperatures. Ta_m = omega^2 R_m g^3 / nu^2 x 1/F_g (Eq. 1), R_m = b / ln((R_i + b)/R_i) with b = A / (2 pi R_i), F_g = (pi^4 / (1697 P)) (R_i + R_o) / (2 R_i) (Eq. 2; the digits are printed as "1967" in the text layer and "1697" is Taylor's critical value quoted on the same page; the page image should be re-read before coding), P = 0.0571 (1 - 0.652 g/R_i) + 0.00056 (1 - 0.652 g/R_i)^-1 (Eq. 3; printed "0652" in the page image, read as 0.652). **The symbol A in b = A / (2 pi R_i) is not defined in the text read**, so Ta_m cannot be evaluated exactly as the paper defines it. This is an open question for the plan; no value is assumed here.
- **Scatter:** none stated as a number. Fig. 10 plots the CFD points beside the fit and the points lie close to it; this was looked at, not digitised, and no band is read from it. The paper says Nu never exceeded the smooth-cylinder correlation of Becker and Kaye ("Nu = 1 for Ta_m < Ta_c; Nu = 0.064 Ta_m^0.367 for Ta_c < Ta_m < 10^4; Nu = 0.205 Ta_m^0.241 for 10^4 < Ta_m < 10^6", p. 3, Ta_c = 1740 non-adiabatic, p. 2).
- **Below the fitted range:** the CFD heat transfer "for low value of Ta_m is below unity Nu" (p. 6), and the fit gives Nu 0.47 at Ta_m = 100. The conduction limit Nu = 1 belongs to the smooth Becker and Kaye case, so Nu = 1 is **not** a cited floor for the salient rotor. No cited correlation exists below Ta_m = 100 or above 3e4; the paper names 10 000 r/min (Ta_m about 1e5) as future work.
- **Grade B:** CFD, one 8/6 geometry, one gap ratio, smooth stator.

### 6.3 Natural convection (item 6d)

- **Horizontal cylinder:** Nu_D = [0.60 + 0.387 Ra_D^(1/6) / (1 + (0.559/Pr)^(9/16))^(8/27)]^2, isothermal cylinder; the `ht` documentation (https://ht.readthedocs.io/en/latest/ht.conv_free_immersed.html) gives the lower Ra limit 1e-5 from Churchill and Chu and the upper limit 1e12 from Bergman et al. 6th ed. 2011, and no error figure. Reference: S. W. Churchill and H. H. S. Chu, Int. J. Heat Mass Transfer 18(9), 1049-1053, 1975, doi:10.1016/0017-9310(75)90222-7. The original was not read.
- **Vertical plate:** Nu_L = [0.825 + 0.387 Ra_L^(1/6) / (1 + (0.492/Pr)^(9/16))^(8/27)]^2, isothermal; Churchill and Chu, Int. J. Heat Mass Transfer 18(11), 1323-1329, 1975, doi:10.1016/0017-9310(75)90243-4; no Ra range and no error given on the `ht` page. The end caps are circular; Faiz 2009 p. 4 replaces each vertical circle of diameter D by a square of equal area (its Eq. 5) with its source [17] (Markovic et al., 2006, not read).
- **Accuracy:** **not found** for either.
- **A cited h for one motor** (Faiz 2009, p. 4 and p. 5, 8/6 SRM, OD 125 mm, computed with those correlations): natural convection 5.2 W/(m2 K) over the frame and 5 W/(m2 K) over the lateral surfaces; forced 30 W/(m2 K) at 4 m/s over the frame; 70 W/(m2 K) at 1000 r/min over the inner stator pole and winding surfaces. These are results for that machine and are not carried to another; radiation is not included in them and Faiz notes it may matter (p. 5).
- **Air properties:** Faiz 2009 Table III (an image in the PDF, cited there to Markovic et al.) is not transcribed here; the code needs air k, nu, Pr, beta against temperature and no source for that table was read to the end. **Not found** for this task.

### 6.4 Oil spray and the other oil options

**End winding spray, measured h (item 6e).** Two measured sources, with rigs that differ by a factor of about five in h; neither carries over to the other.

1. F. Hoffmann, J. Bender, M. Parche, T. Wetzel, M. Doppelbauer (KIT), "Local Heat Transfer Coefficient Measurements on Shaft Spray Cooled End Windings" (6-page manuscript, venue not stated in the file; KIT record https://publikationen.bibliothek.kit.edu/1000163087). Four radial 1 mm holes in a rotating shaft spray the end winding (p. 3); a silicone model end winding of inner diameter 115 mm on a stator of inner diameter 110 mm, 36 slots; **model fluid** water-glycerol (about 11 % water) at 54 to 68 degC, chosen to match the Prandtl number of transmission oils at 60 to 90 degC (p. 2 and 3); flow per hole 0.5 to 0.7 l/min (system 5.6 l/min over eight holes); speed -10 000 to 10 000 r/min. Read from Fig. 4 and Fig. 5 (p. 4), about, off the sump: **3500 to 4800 W/(m2 K)**, with a sump at the 180 degree position **1100 to 2700 W/(m2 K)**; the speed has a minor influence. Model, p. 5, Eq. 9: Nu = ratio_spray x 2.29 x Re^0.28 x Pr^(1/3), ratio_spray = asin(b_MEL / d_in,stator) x num_holes / pi = 0.14 for this rig (Eq. 5), Re = v_F d_0 rho / nu with v_F = sqrt((V / (pi d_0^2 / 4))^2 + (omega r_shaft)^2) (Eq. 7 and 8), d_0 = 1 mm. The mean absolute percentage error is 10.8 % and 93 % of the points are inside +-25 % (p. 6, Fig. 8); the fit leaves out points in a sump. The paper restricts the correlation to the investigated parameters (spray distance, axial offset and stator inner diameter were not varied). **The length scale of Nu is not stated in the text**; d_0 fits the magnitudes of Fig. 8 but that is an inference, so the code takes h from the measured range and not from Eq. 9. Properties of the model fluid are not tabulated in the text read. Grade B.
2. P. Shams Ghahfarokhi, A. Podgornovs, A. J. Marques Cardoso, P. Rasilo, "Assessment of nozzle performance in high-viscosity oil spray system for rectangular copper conductors", Int. J. Thermal Sciences 204, 109244, 2024 (open access; https://homepages.tuni.fi/paavo.rasilo/pubs/ShamsGhahfarokhi2024.pdf). A heated rectangular hairpin conductor sprayed by seven nozzle types, a fixed distance, oil of kinematic viscosity 1e-5 m2/s at 40 degC and 2.7e-6 m2/s at 100 degC and density 0.84 at 15 degC (Table 1, p. 3; the unit is misprinted kg/m3), nozzle pressure 1 to 4 bar, flow 0.65 to 1.5 l/min (Fig. 4 and 5, pp. 5 and 6). Read from Fig. 5 (p. 6): **about 190 to 910 W/(m2 K)** across all nozzles and operating points (190 for a wide full cone at 1 bar, 910 for the 90 degree flat fan at 4 bar), the hollow cone nozzle flat near 270 to 290. Measurement uncertainty of h +-6.08 % (p. 5). The oil inlet temperature is not given in the text read. Grade B.

A CFD paper (UKHTC 2024 paper 73) gives 530 W/(m2 K) for a 2 mm radial nozzle at 75 kg/min; it is a simulation and is not used.

**Shaft oil cooling to the rotor (item 6f): not found.** Neither paper above is about oil to a rotor through the shaft bore, and no other source was read. The code refuses this option.

**Slot oil channel (item 6g): not found.** Marquez-Fernandez 2018 (p. 4) says the coolant flow model uses Darcy-Weisbach resistances and takes the convection coefficients from the flow model, and prints no h and no Nusselt correlation. Its coolant is water (6 to 9 l/min, Section V, p. 4 and 5). A water-glycol slot channel is a duct problem and uses item 6a and 6b; an oil slot channel has no property data (see 6.7). The code refuses a slot-oil option with oil.

### 6.5 Stator-housing contact (item 6h): not found

The source that this brief named, Staton, Boglietti and Cavagnino, IEEE Trans. Energy Convers. 20(3), 620-628, 2005 (cited as [15] in Faiz 2009), was not reachable (403 at iris.polito.it; scispace returned an empty page; core.ac.uk 403). Web search summaries describe a table of lamination-to-housing equivalent air gaps of 0.042 mm (4 kW), 0.076 mm (7.5 kW) and 0.077 mm (15 kW), all totally enclosed induction motors, with a conversion using air k = 0.026 W/(m K) and a rough-finish value of 0.023 mm from Janna; they are not an opened document and are **not recorded as values**. The Simpson, Wrobel, Booker and Mellor interface paper (IET PEMD 2016, doi:10.1049/cp.2016.0129) has no full text in the repository found and its abstract states no gap. Faiz 2009 gives no contact value. No range with a fit type is on record. The default and the band of `stator_housing_contact` cannot be coded; the plan needs the owner's value or a read copy of Staton 2005.

### 6.6 Slot liner, resin, housing and winding (items 6i to 6k, 6m)

| Item | Value | Source and page | Grade |
|---|---|---|---|
| Slot liner | 0.076 W/(m K), density 2150 kg/m3, specific heat 1172 J/(kg K) | Faiz 2009 Table II (image, PDF p. 2), "thermal parameters [3], [16]", single value, no range | C |
| Slot wedge | 0.29 W/(m K) | Faiz 2009 Table II | C |
| Nomex 410 | 0.103 (50 um), 0.114 (80), 0.123 (130), 0.143 (180), 0.139 (250), 0.149 (380), 0.157 (510), 0.175 W/(m K) (760 um); no test temperature or standard on the page | SynFlex Elektro product page "Syn_Therm Nomex 410", Thermal table, https://www.synflex.com/en/system-seiten/product-1/nomexr-410-403 | C (distributor table, DuPont data sheet not reached) |
| Impregnation epoxy | "ranging from 0.6 to 1 W/(m K)", actual value not known, depends on fillers | Marquez-Fernandez 2018, PDF p. 8 | B |
| Winding, equivalent (random wound) | 0.6 to 0.9 W/(m K), used 0.83 | Faiz 2009 pp. 3 (text), citing [3], [14] | C |
| Copper along the wire | 300 W/(m K) used by the authors | Marquez-Fernandez 2018, PDF p. 3 | B (their model input) |
| Aluminium 6061-T6, 77 F | 167 W/(m K) typical; 6061-O 180, 6061-T8 170 | MatWeb "ASM Material Data Sheet" pages, quoted by a search result (https://asm.matweb.com/search/specificmaterial.asp?bassnum=ma6061t6); not opened (connection refused) | C |
| Frame, aluminium | 177 W/(m K), 875 J/(kg K), 2770 kg/m3 | Faiz 2009 Table II | C |
| Stator lamination | 20 W/(m K), 438 J/(kg K), 7650 kg/m3 | Faiz 2009 Table II (10JNEX900: 18.6 in section 1) | C |

A380 die casting: values from search results run from 92 to 130 W/(m K) and no data sheet was reached, so no value is recorded for it. Nomex values rise with thickness; the table gives no value at 300 and 610 um.

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

### 6.8 Cross-wire winding conductivity (item 6m)

Marquez-Fernandez 2018, PDF p. 7 (Eq. 5) and p. 8 (Eq. 6 and the text after it). Symbols: lambda_i conductivity, theta_i volume fraction of material i, sub-index 1 copper and 2 the potting epoxy, xi a parameter that depends on the fill factor ("for K_f = 0.37 equals 0.324"), after Idoughi et al., IEEE Trans. Magn. 47(12), 4822-4826, 2011 (their ref. [18]; not read) and Milton, J. Appl. Phys. 52, 5294-5304, 1981 ([19]; not read).

- **Hashin-Shtrikman, Eq. (5) as printed:** lambda_HS = lambda_2 ((1 + theta_1) lambda_1 + (1 - theta_2) lambda_2) / ((1 - theta_1) lambda_1 + (1 + theta_2) lambda_2).
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

### 6.9 Lamination conductivity scatter (item 6n): not found

Values on record: 18.6 W/(m K), direction not stated (Ou et al. 2021 Table I, section 1; grade C) and 20 W/(m K) (Faiz 2009 Table II; grade C; an unrelated steel). No source read states a scatter. A search result describes NREL measurements of M19 and other grades at 20 to 23 W/(m K) in the bulk and 0.7 to 2.1 W/(m K) effective through-stack, with through-stack values that vary by 200 % or more with contact resistance; those papers were not reachable and are **not recorded as values**. The plan's call of **12 W/(m K)** for the low end has no source behind it: it is an owner-level placeholder carried by the plan, labelled as such in section 7, and the row stays open until a grade A or B value exists.

## 7. Bands

One row for each budget row of spec §7 that needs a band. "Nominal" is what the model uses. "Unfavourable" is the end the worst-case stack uses. A row marked **no band** has no cited unfavourable end and the code must either refuse the option or take the value from the owner; it never takes a number from this table that is not written here.

| Row | Nominal | Unfavourable end | Where it comes from | Status |
|---|---|---|---|---|
| `cross_wire` | Milton, Eq. (6), xi 0.324, at fill 0.37 only, with the resin of the next row; for any other fill xi is **not found**, so the nominal is the HS value of Eq. (5) | the HS value of Eq. (5) at the same fill and resin: 11 % below Milton at fill 0.37 and 20 % below at 0.47 (section 6.8) | section 6.8; the HS value lies below the Milton value in the four cases computed; HS is the "lower check" of spec §6.3; the paper says Milton may itself be low | band found for fill 0.37, HS-only (zero width) for other fills |
| `liner` | Nomex 410 by thickness from the SynFlex table, 0.103 to 0.175 W/(m K) | 0.076 W/(m K) (Faiz 2009 Table II, the lowest value on record) | 6.6 | band found, grade C, no temperature or test method |
| `impregnation` (resin, in the same spec row as the liner) | 1.0 W/(m K), the value the authors simulated (Milton 2.41 at fill 0.37) | 0.6 W/(m K) | Marquez-Fernandez 2018 p. 8 | band found, grade B |
| `contact` | none | none | 6.5 | **no band**, not found |
| `air_gap` | Romanazzi and Howey, Nu = 0.181 Ta_m^0.207 for Ta_m 1e2 to 3e4 | none stated by the paper | 6.2 | **no band**, no scatter number; outside 1e2 to 3e4 no correlation; Ta_m needs the undefined A |
| `cooling_h` jacket (water-glycol) | Gnielinski with the 50 wt % properties at 65 degC (Re 3000 to 5e6); laminar only for a square channel | h at minus 10 % | 6.1 and 6.7; the 10 % is second-hand and marked uncertain on its source page | band found, grade C |
| `cooling_h` end space (natural convection) | Churchill and Chu; air properties not found | none | 6.3 | **no band** (no accuracy found; air property table not transcribed) |
| `cooling_h` end spray | the measured range of the chosen rig: nozzle spray on a hairpin 190 to 910 W/(m2 K), or shaft spray 3500 to 4800 W/(m2 K) | the low end of that range, or for the shaft spray inside a sump 1100 W/(m2 K); the Hoffmann model adds minus 25 % | 6.4; neither rig is the owner's geometry | measured ranges found, two disjoint rigs, selection is the plan's |
| `cooling_h` shaft oil | none | none | 6.4 | **not found**, option refused |
| `cooling_h` slot oil | water-glycol: as the jacket row; oil: none | water-glycol: minus 10 % | 6.4 | oil **not found**, option refused with oil |
| `lamination_k` | 18.6 W/(m K) | 12 W/(m K) | the plan's call, no source (6.9) | **placeholder**, ungraded |

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
| Flow | 8 L/min = 1.333e-4 m3/s |
| Housing thickness | 8 mm |

Check of the flow regime this gives (arithmetic only, with the 65.6 degC properties of section 6.7): hydraulic diameter 2 h w / (h + w) = 6.67 mm, section 80 mm2, mean speed 1.67 m/s, Re about 9800, inside the Gnielinski range.

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

The measured-agreement values are **24 % above** the Milton ones (3.0 / 2.41 = 1.245; 3.85 / 3.11 = 1.238 using the printed 3.11). The paper does not state the agreement as a number; it says only that the higher value gives "a better agreement" (pp. 8 and 9). So V3 as designed in spec §8 has: model input 2.41 or 3.11 (3.44 by this file's arithmetic for fill 0.47), and a better-fit value about 24 % higher, from one coil type each, with no temperature error reported as a number. A gate threshold must be set from the plan; the paper gives none.
