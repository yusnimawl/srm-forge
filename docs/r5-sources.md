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
| 2 | Copper k, c, expansion | National Bronze C11000 data sheet p. 2 (CDA values) | B | found |
| 3 | steel_1010 k, c, expansion, E, Poisson ratio, yield | Elgin Fasteners grade 1010 data sheet pp. 1-3 | C | found, cold-drawn condition |
| 4 | Kt of a shoulder fillet in tension | AmesWeb calculator page quoting Pilkey 2005 | C | formula found, book page not recorded, to be checked against Peterson (gate V6 interim) |

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

Source: National Bronze Manufacturing, C11000 (Electrolytic Tough Pitch) data sheet, https://www.nationalbronze.com/pdfs/C11000.pdf, PDF page 2, "Physical Properties" (US customary, the values are those the Copper Development Association publishes for C11000). The CDA page itself (alloys.copper.org) was under maintenance and the CDA fact sheet returned 403, so neither was read.

| Quantity | As printed | SI used |
|---|---|---|
| Thermal conductivity | 226 Btu ft/(hr ft2 F) at 68 F | 391.1 W/(m K) (x 1.7307) |
| Specific heat | 0.092 Btu/lb/F at 68 F | 385.2 J/(kg K) (x 4186.8) |
| Expansion | 9.40e-6 per F (68-212 F); 9.60e-6 (68-392 F); 9.80e-6 (68-572 F) | 1.692e-5 per K (x 1.8, the 20-100 degC range) |

Grade B (a manufacturer data sheet quoting CDA, typical values). The library copper is the IEC annealed standard for resistivity; C11000 is the matching commercial grade (101 % IACS). Modulus of elasticity in tension 17000 ksi is on the same page but no copper `mechanical` block is added (not needed for R5a).

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

Neither Peterson nor Roark was reachable. The formula below was read from the AmesWeb page "Stress Concentration Calculator - Shoulder Fillets in a Flat Bar", https://amesweb.info/stress-concentration-factor-calculator/shoulder-fillets-in-flat-bar.aspx, which gives as its reference Pilkey, W. D. (2005), Formulas for Stress, Strain, and Structural Matrices, 2nd ed., Wiley ). The book page is not recorded: a page number "p. 156" for Peterson's Stress Concentration Factors (2nd ed., Pilkey 1997) is only an inference from the EES page "Rod with shoulder fillets under tension" (https://fchartsoftware.com/ees/mechanical_design/stress_concentration_factors/hs203.htm), which gives no formula, only one example, and says "rod", not flat bar. The source actually read is a calculator page quoting Pilkey 2005. Grade C. The coefficients and the D/d range still need checking against Peterson; gate V6 is the interim check.

Geometry (figure on the page): opposite shoulder fillets in a stepped flat bar; D = width of the wide part, d = width of the narrow part, h = step height = (D - d)/2 (drawn in the figure), r = fillet radius, L = length of the wide part, t = thickness. Load P in tension, nominal stress sigma_nom = P / (t d), sigma_max = Kt sigma_nom.

Kt = C1 + C2 (2h/D) + C3 (2h/D)^2 + C4 (2h/D)^3, with s = sqrt(h/r) and x = h/r:

| | 0.1 <= h/r <= 2.0 | 2 <= h/r <= 20 |
|---|---|---|
| C1 | 1.006 + 1.008 s - 0.044 x | 1.020 + 1.009 s - 0.048 x |
| C2 | -0.115 - 0.584 s + 0.315 x | -0.065 - 0.165 s - 0.007 x |
| C3 | 0.245 - 1.006 s - 0.257 x | -3.459 + 1.266 s - 0.016 x |
| C4 | -0.135 + 0.582 s - 0.017 x | 3.505 - 2.109 s + 0.069 x |

Validity as printed: the h/r ranges above, and L/D > -1.89 (r/d - 0.15) + 5.5 (a long enough wide part). The page gives no range for 2h/D. Task 6 refuses or clamps outside the printed h/r range (0.1 to 20). At 2h/D = 0 the fit returns C1, about 1 + sqrt(h/r), the semi-infinite-plate limit (1.32 at h/r = 0.1), a real value. The formula is for a plate in plane stress; a rotor bridge or pole root is not an isolated step, so it is a screening estimate.
