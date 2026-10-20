# R3 loss sources

Literature search for the R3 losses work (spec `docs/superpowers/specs/2026-10-18-r3-losses-design.md`, sections 3, 4 and 9). Everything below was read from the cited documents on 2026-10-17. Nothing is invented: where a value could not be found, this file says so.

Grades: **A** measured table, **B** measured or manufacturer figure, read off or traced from the vector drawing, **C** typical, derived or secondary source.

## Summary

| # | Item | Source | Grade | Status |
|---|---|---|---|---|
| 1a | 10JNEX900 sinusoidal W/kg vs B and f | JFE f1e-002 sample table (7 anchor points) and f2e-001 pp. 4 and 8 (curves) | A (anchors), B (curves) | found |
| 1b | 10JNEX900 resistivity | JFE f1e-002 sample table, 0.82 uOhm m | A | found |
| 2a | M19 W/kg vs B and f | AK Steel Di-Max M-19, 0.014 in, via Lamination Steels 3rd ed. (EMERF), MIT OCW excerpt p. 5 | A | found (licence restricts redistribution) |
| 2b | M19 resistivity | only a secondary reference (ASTM A677 typical range 45 to 55 uOhm cm) | C | no datasheet value found |
| 3 | DC-bias hysteresis factor | Urgera thesis 2024 Tables 5.3 and 5.4 (measured); Zhu et al. 2019 Fig. 18 | A (thesis), B (Zhu) | found, but the exponent is not 2 (see below) |
| 4 | Materu measured core and copper loss, 6/4 | Materu dissertation 1989, Tables 4 and 5 pp. 97 and 98 | A | found, gate passed with caveats |
| 5 | Cross-check candidates | see the last section | not graded | 4 candidates, 3 full texts not retrievable |

Files downloaded for reading are kept outside the repo (scratchpad `r3dl/`). No PDF was added to the repo: the Materu dissertation (Virginia Tech, vtechworks, no licence statement), the EMERF/AK Steel tables (OCW licence forbids incorporating them in software) and the Newcastle thesis (all rights reserved) are not clearly redistributable. URLs and pages are recorded instead.

## 1. 10JNEX900 (JFE Super Core JNEX-Core, 0.10 mm)

### 1a. Core loss, sinusoidal flux, W/kg

Conditions of every figure: 25 cm Epstein frame, specimens parallel to the rolling direction, as-sheared, assumed density 7.49 kg/dm3, 0.10 mm.

**Anchor values (grade A, tabulated)**: `docs/sources/materials/jfe_f1e-002_super_core.pdf`, PDF page 5, "Sample Characteristics Table" (JFE in-house data, typical; the library JSON cites this table as p. 4). Row JNEX-Core 0.10 mm:

| W10/50 | W10/400 | W10/1k | W5/2k | W2/5k | W1/10k | W0.5/20k |
|---|---|---|---|---|---|---|
| 0.5 | 5.7 | 18.7 | 13.7 | 11.3 | 8.3 | 6.9 |

W a/b means peak flux density a/10 T at b Hz (W10/50 is 1 T at 50 Hz, W5/2k is 0.5 T at 2 kHz, W2/5k is 0.2 T at 5 kHz, W1/10k is 0.1 T at 10 kHz, W0.5/20k is 0.05 T at 20 kHz), in W/kg. The same row is in the German edition `jfe_f1g-001_super_core_de_from_jystator.pdf` (table "Eigenschaftentabelle", with decimal commas). The product table of f1e-002 (PDF page 5, "Product Dimensions and Specifications") guarantees W10/400 of 9.0 W/kg or less, space factor 90 % or more, density 7.49 g/cm3.

**Curves (grade B)**: `docs/sources/materials/jfe_f2e-001_magnetic_property_curves.pdf`:

- p. 4, "High-Frequency Core Loss Curves": B (0.001 to 1 T, log) against W (0.01 to about 3000 W/kg, log), 11 curves at 50, 100, 200, 400 Hz, 1, 2, 5, 10, 20, 30, 50 kHz. The curves are vector paths in the PDF; they were read from the Bezier paths (axis calibration from the decade gridlines; curve identity checked by monotonic order and against the anchor values). The table below samples them. Each curve covers only part of the B range (the 50 Hz curve starts near 0.13 T, the 50 kHz curve ends near 0.5 T), a dash means outside the drawn range.
- p. 8, "Core Loss Curves" at 50 Hz and 60 Hz, B 0.5 to 1.4 T on a linear axis, W 0.01 to 10 W/kg log (table below).
- pp. 9 to 11: 50 Hz magnetisation curve, excitation curve, exciting power (not loss data).

W/kg read from p. 4 (three significant figures; the drawn curves are typical, the read-off error from the vector path is below 1 %, the scatter of the real material is not stated):

| f (Hz) | 0.02 T | 0.05 T | 0.1 T | 0.2 T | 0.3 T | 0.5 T | 0.7 T | 1.0 T |
|---|---|---|---|---|---|---|---|---|
| 50 | - | - | - | 0.0223 | 0.0484 | 0.129 | 0.248 | 0.506 |
| 100 | - | - | 0.0154 | 0.0559 | 0.118 | 0.301 | 0.558 | 1.15 |
| 200 | - | 0.011 | 0.0398 | 0.141 | 0.285 | 0.686 | 1.26 | 2.65 |
| 400 | - | 0.0241 | 0.0839 | 0.29 | 0.597 | 1.49 | 2.75 | 5.59 |
| 1000 | 0.0127 | 0.0751 | 0.276 | 1.01 | 2.15 | 5.48 | 10 | 18.7 |
| 2000 | 0.0337 | 0.189 | 0.7 | 2.53 | 5.24 | 13.4 | 25.7 | 53.5 |
| 5000 | 0.176 | 0.93 | 3.24 | 11.2 | 23.1 | 58.5 | 111 | - |
| 10000 | 0.43 | 2.45 | 8.77 | 30.2 | 62.2 | 161 | 308 | 622 |
| 20000 | 1.23 | 7.26 | 27.8 | 100 | 204 | 495 | 881 | - |
| 30000 | 2.46 | 14 | 51.2 | 180 | 375 | 998 | 1950 | - |
| 50000 | 6.1 | 35.5 | 131 | 458 | 946 | 2350 | - | - |

Check against the grade A anchors: W10/50 0.506 (0.5), W10/400 5.59 (5.7), W10/1k 18.7 (18.7), W5/2k 13.4 (13.7), W2/5k 11.2 (11.3), W1/10k 8.77 (8.3, +5.7 %), W0.5/20k 7.26 (6.9, +5.2 %). The curves agree with the anchors within 6 %.

W/kg read from p. 8 (linear B axis; the vector curve for 50 Hz agrees with p. 4 at 1 T, 0.509 against 0.506):

| B (T) | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 | 1.1 | 1.2 | 1.3 |
|---|---|---|---|---|---|---|---|---|
| 50 Hz | 0.189 | 0.248 | 0.319 | 0.404 | 0.509 | 0.649 | 0.843 | 1.079 |
| 60 Hz | 0.223 | 0.292 | 0.378 | 0.487 | 0.624 | 0.799 | 1.026 | 1.27 |

The curves are drawn up to 1.4 T; the 1.4 T end of each curve is nearly vertical in the plot and is not tabulated here. The sample table gives saturation magnetisation 1.80 T, B8 1.29 T, B25 1.40 T.

Derived (grade C): between 0.1 and 0.5 T the log-log slope of W against B is 1.77 to 1.86 at every frequency from 100 Hz to 50 kHz (about 1.8), so a fixed flux exponent near 1.8 is consistent with the figure over that range. Loss separation into hysteresis and eddy parts is not given by the manufacturer; any fit is the project's own.

Not in the JFE material: loss under non-sinusoidal flux, under DC bias, or on cut (punched, laser) laminations. The catalogue says the properties degrade little with machining, with no figure.

### 1b. Resistivity

0.82 uOhm m (82 uOhm cm), JFE f1e-002 PDF page 5 sample table, column "Specific resistance", grade A (typical in-house value). The f2e-001 curves book has no resistivity value. The JFE technical report 21 p. 46 (`jfe_technical_report_21_p46_jnsf.pdf`) says only that the resistivity of 6.5 % Si steel is nearly 2 times that of 3 % Si steel.

## 2. M19 (AK Steel Di-Max M-19, now Cleveland-Cliffs, ASTM A677 36F155)

### 2a. Core loss

Source: Sprague, S. (ed.), *Lamination Steels, Third Edition*, EMERF (Electric Motor Education and Research Foundation), 2007, CD-ROM, "AK Steel Di-Max M-19, Fully Processed, .014 inch (.36 mm, 29 gauge)", total core loss data; excerpt published on MIT OpenCourseWare 6.685 (Fall 2013), problem set 3 data, 7-page PDF, **page 5** "Total Core Loss - Pc vs. B": https://www.ocw.mit.edu/courses/6-685-electric-machines-fall-2013/64bf1faf0a973d9607334321dd252794_MIT6_685F13_ps03data.pdf . Grade A (tabulated). The table gives "typical total AC core loss of as-sheared .014 inch (.36 mm, 29 gauge) Di-Max M-19 ... values from previously unpublished information provided by AK Steel, 2000"; W/kg were derived by EMERF as W/lb x 2.204. The page also says "Information on this page is not guaranteed or endorsed ... Confirm material properties with material producer prior to use." Page 2 of that PDF has the magnetisation data, page 6 the exciting power.

Licence: the excerpt states that unauthorised duplication and distribution, and incorporation of the information in other publications or software, without EMERF authorisation, is prohibited. The numbers below are a transcription for the owner's check (data are facts, but the owner should decide before they go into a library JSON that ships); the PDF is not in the repo.

Total core loss, W/kg (the red column of the table; the W/lb column is in the PDF). B in tesla = gauss / 10000. A dash means the table has no entry.

| B (T) | 50 Hz | 60 Hz | 100 Hz | 150 Hz | 200 Hz | 300 Hz | 400 Hz | 600 Hz | 1000 Hz | 1500 Hz | 2000 Hz |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.1 | 0.0176 | 0.0198 | 0.0375 | 0.0639 | 0.0926 | 0.163 | 0.247 | 0.452 | 1.02 | 1.98 | 3.20 |
| 0.2 | 0.0683 | 0.0860 | 0.159 | 0.262 | 0.381 | 0.661 | 0.994 | 1.79 | 3.94 | 7.43 | 11.7 |
| 0.4 | 0.240 | 0.295 | 0.555 | 0.934 | 1.37 | 2.39 | 3.60 | 6.52 | 14.0 | 26.1 | 40.8 |
| 0.7 | 0.602 | 0.749 | 1.43 | 2.44 | 3.61 | 6.44 | 9.81 | 18.0 | 39.1 | 74.3 | 119 |
| 1.0 | 1.09 | 1.36 | 2.61 | 4.50 | 6.74 | 12.2 | 18.9 | 35.7 | 80.0 | 158 | 257 |
| 1.2 | 1.51 | 1.89 | 3.63 | 6.30 | 9.46 | 17.3 | 26.9 | 51.8 | 120 | 240 | 395 |
| 1.3 | 1.79 | 2.23 | 4.28 | 7.41 | 11.2 | 20.3 | 31.8 | 61.3 | 143 | 291 | - |
| 1.4 | 2.14 | 2.66 | 5.09 | 8.82 | 13.2 | 24.1 | 37.5 | - | - | - | - |
| 1.5 | 2.56 | 3.19 | 6.11 | 10.5 | 15.8 | 28.7 | 44.4 | - | - | - | - |
| 1.55 | 2.77 | 3.44 | 6.59 | 11.4 | 17.0 | 30.7 | 47.6 | - | - | - | - |
| 1.6 | 2.96 | 3.67 | 7.01 | 12.0 | 18.0 | - | - | - | - | - | - |
| 1.65 | 3.13 | 3.89 | 7.44 | 12.8 | 19.1 | - | - | - | - | - | - |
| 1.7 | 3.29 | 4.08 | 7.80 | 13.4 | 20.1 | - | - | - | - | - | - |
| 1.8 | - | 4.40 | - | - | - | - | - | - | - | - | - |

Check against the W/lb column (x 2.204): 1.0 T 60 Hz 0.617 W/lb gives 1.36 W/kg; 1.5 T 60 Hz 1.45 W/lb gives 3.20 W/kg (table 3.19). Consistent. The ASTM A677 maximum for 36F155 at 1.5 T, 60 Hz is 1.55 W/lb (3.4 W/kg), against the typical 1.45 W/lb here (secondary source for the standard value: a table reproduced by a third-party site that could not be re-fetched).

A fitted curve (grade C, secondary): Kirtley, MIT 6.061 notes (OpenCourseWare, CC BY-NC-SA 4.0), Table 1, 29-gauge fully processed M-19: P = P0 (B/B0)^eB (f/f0)^eF with B0 = 1 T, f0 = 60 Hz, P0 = 0.59 W/lb (1.30 W/kg), eB = 1.88, eF = 1.53 (fit to the same family of data; useful as a sanity check of the table above: at 1 T, 60 Hz the table gives 1.36 W/kg).

### 2b. Resistivity and density

- Resistivity: no datasheet value was found. The only value found is a secondary one: ASTM A677 typical electrical resistivity of 45 to 55 uOhm cm for M-19 (36F155) as reproduced by a third-party table (search result summary; the page returned 404 when fetched again). Grade C. A manufacturer datasheet (Cleveland-Cliffs or the AK Steel Di-Max bulletin) was not retrievable. The repo's own material file `src/srmcore/materials/data/M19.json` already marks density 7650 kg/m3 as provisional.
- Density 7.65 g/cm3: appears in a search-result summary of an MIT 6.061 "steel data" sheet for the same AK Steel product; the page itself could not be fetched, so this is unverified.

## 3. DC-bias hysteresis factor

Form used in the literature (Simao et al., IEEE Trans. Magn. 45(3), 2009, pp. 1158-1161, as cited by Zhu et al.): the hysteresis loss of a loop with DC bias is the unbiased loss times

    epsilon(B_bias) = 1 + k_DC * B_bias^alpha

**The exponent alpha is not 2 in any measured set found.** The spec writes the factor as (1 + k_dc B_dc^2); the data below give alpha between 2.15 and 5.2, with the best single-set fits near 3.8 to 5. The plan should either carry alpha as a parameter or fix k_DC for alpha = 2 only if it is refitted to the data below.

**Measured on toroids (grade A)**: Urgera, G., *Modelling and Dynamic Analysis of Switched Reluctance Drives*, PhD thesis, Newcastle University, 2024, http://hdl.handle.net/10443/6496 (PDF theses.ncl.ac.uk/jspui/bitstream/10443/6496/1/Urgera%20G%202024.pdf; rights: all rights reserved, so not copied into the repo). Section 5.5, Eq. 5.7 (P_dc = (1 + k_DC B_bias^alpha_DC) P_sin for the hysteresis part), M250-35HS (0.35 mm non-oriented), two toroidal samples with AC and DC windings, ambient temperature, B_bias up to 0.6 T, 100 Hz to 1 kHz:

| Table | Condition | k_DC | alpha_DC |
|---|---|---|---|
| 5.3 (p. 89) | B_ac = 1.1 T | 0.47 | 2.15 |
| 5.3 | B_ac = 0.9 T | 2.54 | 4.6 |
| 5.3 | B_ac = 0.86 T | 1.59 | 4.03 |
| 5.3 | B_ac = 0.8 T | 2.42 | 5.21 |
| 5.4 (p. 90) | single set, all data (geometric mean) | 1.4664 | 3.7955 |

The thesis states that one set for all amplitudes is "a significant approximation"; the eddy coefficient was reduced from 3.53e-6 to 2.8e-6 before the hysteresis part was separated.

**Second source (grade B, read off a figure)**: Zhu, Z. Q., Xue, S., Chu, W. et al., "Evaluation of Iron Loss Models in Electrical Machines", IEEE Trans. Ind. Appl. 55(2), 2019, pp. 1461-1472, accepted version at https://eprints.whiterose.ac.uk/id/eprint/146185/ , Eqs. 14, 15, 17 and Fig. 18 (PDF page 10): steel V300-35A (0.35 mm), ring specimen; k_DC about 0.9 to 1.0 and alpha about 4.7 to 5.0 over 40 to 100 C (read from the plot, both rise slowly with temperature). The IPM test machine data in Fig. 19 follow Eq. 16 within the plot scatter.

Not retrieved: Zhu S., Cheng M., Dong J., Du J., IEEE Trans. Ind. Electron. 61(10), 2014, pp. 5203-5212 (functional relation between DC-biased induction and hysteresis loss; full text not available); de la Barrière et al., IEEE Trans. Magn. 55 (2019), "Loss Prediction in DC-Biased Magnetic Sheets" (Preisach based, no closed-form k_DC; shows non-oriented Fe-3.5Si loops with bias 0.75 T).

Relevance to 10JNEX900 and M19: both sources are 0.35 mm 3 % Si steels; no DC-bias data for 6.5 % Si or for M19 were found. Applying these coefficients to 10JNEX900 is an extrapolation (grade C).

## 4. Materu measured core and copper loss, 6/4 SRM

Source: Materu, P. N., *Design and steady-state analysis of the switched reluctance motor drive*, PhD dissertation, Virginia Polytechnic Institute and State University, 1989. https://vtechworks.lib.vt.edu/items/08c8fa09-b093-44fd-9db9-c7486164fd6d (handle http://hdl.handle.net/10919/109954; PDF 10 MB, 321 pages; no licence statement on the page). Printed page numbers below (the PDF page index is the printed number plus 15). Chapter 3, "Estimation of switched reluctance motor losses". The related conference paper (Materu and Krishnan, "Estimation of switched reluctance motor losses", Conf. Rec. IEEE-IAS Annual Meeting, Pittsburgh, 1988, pp. 79-90, DOI 10.1109/IAS.1988.25045) was not read.

### Gate (plan step 2) assessment

The measured data and their conditions are in the dissertation, so the gate is passed. The gaps that limit a reproduction are listed after the data. The owner decides whether they are acceptable.

### Data (grade A, tabulated): Tables 4 and 5, pp. 97 and 98 (PDF pp. 112, 113; checked against the page images)

Conditions common to both tables (p. 89): the 6/4 laboratory prototype coupled to a d.c. dynamometer; **fixed supply voltage 180 V d.c.** for all measurements (the rated supply in Appendix A is 300 V); current waveforms acquired by a data acquisition system with 1024 points per period; phase resistance 3.4 Ohm.

Table 4, flat-topped current (advance angle 0 deg, conduction angle 18.05 deg, p. 89):

| Peak current (A) | rms current by DAS (A) | rms current by [38] (A) | Iron loss (W) | Copper loss (W) | Speed (rpm) | Pcu/Pin (%) |
|---|---|---|---|---|---|---|
| 1.07 | 0.446 | 0.618 | 5.6 | 2.0 | 955 | 3.4 |
| 1.54 | 0.629 | 0.889 | 9.6 | 4.0 | 729 | 4.8 |
| 1.83 | 0.768 | 1.057 | 10.4 | 6.0 | 615 | 5.9 |
| 2.13 | 0.888 | 1.230 | 10.5 | 8.0 | 550 | 6.9 |
| 2.54 | 1.051 | 1.466 | 10.70 | 11.3 | 486 | 8.0 |

Table 5, peaky current (advance angle 11.95 deg, conduction angle 25.27 deg, p. 89):

| Peak current (A) | rms current by DAS (A) | rms current by [38] (A) | Iron loss (W) | Copper loss (W) | Speed (rpm) | Pcu/Pin (%) |
|---|---|---|---|---|---|---|
| 2.67 | 0.870 | 1.30 | 20.6 | 7.7 | 2324 | 4.5 |
| 3.28 | 1.067 | 1.59 | 11.3 | 11.6 | 1806 | 5.2 |
| 4.04 | 1.356 | 1.96 | 7.3 | 18.8 | 1458 | 7.1 |
| 4.94 | 1.712 | 2.40 | 15.5 | 29.9 | 1150 | 9.0 |
| 5.66 | 2.000 | 2.66 | 22.9 | 40.8 | 1004 | 10.6 |

Also: Figs. 31 and 32 (pp. 95, 96) plot the same data (core and copper loss against peak current, 988 to 2324 rpm peaky, 486 to 955 rpm flat-topped); Table 3 (p. 94) compares average current from a d.c. meter and the DAS; Figs. 34 and 35 (pp. 101, 102) compare the measured core loss with the dissertation's own predictions (from the voltage waveform and from the current waveform; the voltage-based prediction deviates at high saturation). Fig. 33 (p. 99) gives a reconstructed flux linkage waveform for 1095 rpm, peak 5.1 A, conduction 25.3 deg.

Definitions (Section 5.4.3 p. 163, and Eq. 4.24): the advance angle is the angle by which turn-on is advanced before the onset of alignment between the approaching rotor pole and the excited stator pole; the conduction angle is the angle over which the phase is on.

### How the loss was separated (p. 89, Section 3.6)

Input power from the average current and the d.c. supply voltage; the difference from the shaft output power is the total loss. **Core loss = total loss - copper loss - friction and windage - stray load loss.** Copper loss is computed from the DAS rms current and the phase resistance with Eq. 3.39 (the equation text is an image in the PDF; the table values match 3 phases x 3.4 Ohm x I_rms^2, for example 3 x 3.4 x 0.446^2 = 2.0 W), so the copper column is a calculation, not an independent measurement. Friction and windage versus speed was obtained by driving the motor at no load with a permanent magnet d.c. motor of known torque constant and resistance. Stray load loss was **assumed** to be 6 % of the total motor loss (citing reference [62]). The core loss is therefore a difference of larger numbers with an assumed term; the dissertation also quotes core loss increases of up to 25 % from cutting stress and stacking (p. 100).

### Machine (Appendix A, pp. 286 to 288)

6 stator poles and 4 rotor poles; stator pole arc 24 deg, rotor pole arc 36 deg; stator outer diameter 190 mm; bore 122.0 mm (the book value used by the repo is 102.06 mm, see `docs/m5d-krishnan-results.md`); core length 60.37 mm; shaft 28.56 mm; rotor pole height 27.25 mm; stator back iron 10.15 mm; air gap 0.25 mm; 536 turns per phase; rated 300 V, 10 A peak, 1800 rpm, 2.7 kW; core material "E140 steel"; wire AWG 19.

### Gaps and cautions for reproduction

- The loss curve of the core steel ("E140") is not in the dissertation; the model used manufacturer curves (W/lb against B and f, Section 3.4.1, Eqs. 3.33 to 3.35, log-linear fit in f, only the pair of active poles counted in each pole part) that are not reproduced. A substitute (M19, section 2) is a material mismatch of unknown size.
- The control and chopping are not described for the measured points. The speed falls as the peak current rises in both tables (for example 955 to 486 rpm for 1.07 to 2.54 A), which suggests single-pulse operation at 180 V with the speed set by the load, but the text does not say so (this is an inference, not a statement of the source).
- Currents are small (peak 1.07 to 5.66 A against a 10 A rating), speeds 486 to 2324 rpm, total losses 8 to 63 W. The 2D flux deficit of M5d appears only at high current, so these points test the loss model in the lightly saturated range.
- Core loss in Table 5 is not monotonic (20.6, 11.3, 7.3, 15.5, 22.9 W), consistent with subtraction noise and the assumed stray term; Table 4 core loss saturates at 10.4 to 10.7 W above 1.8 A. Uncertainty of the core loss values is large and not stated by the author.
- The dissertation and Krishnan (2001) disagree on the bore and back iron, as noted in `docs/m5d-krishnan-results.md`.
- Krishnan, R., *Electric Motor Drives* (2001), Table 2.3 reprints the inductance data; whether it also reprints these loss tables was not checked.

## 5. Cross-check candidates (owner pick pending)

Selection rule from the spec: a published FEA iron-loss breakdown per region (stator pole, stator yoke, rotor pole, rotor yoke), ideally with a measured total. The full text of three of the four candidates could not be retrieved (HTTP 403 or a bot check from the publisher), so their descriptions come from abstracts and search summaries, and the reproducibility judgement is provisional. Nothing below has a number copied from a paper.

1. **"Method for estimating core losses in switched reluctance motors", European Transactions on Electrical Power, 2010 (author list not confirmed)** (UPCommons http://hdl.handle.net/2117/11193, open access repository; full text not retrieved). A 6/4 SRM, the same pole combination as the Materu machine. The core is split into nine zones (stator poles, stator yoke segments, rotor poles and rotor yoke); eddy-current and hysteresis loss are reported per zone and against speed under constant-current control, with the largest values in the rotor zones and one stator yoke zone, according to the summary found. Whether a measured total accompanies it, and whether the machine dimensions are given in full, is not confirmed. Reproducibility: unknown until the paper is read; the nine-zone breakdown is the closest to what the engine will compute per region.
2. **Li et al., "Iron Loss Calculation in Switched Reluctance Motor Based on Flux Integral Path", Progress In Electromagnetics Research M, 2022** (https://www.jpier.org/PIERM/pier.php?paper=22061306; the journal is open access, but the site returned a bot check, full text not retrieved). A flux-integral-path method for hysteresis and eddy-current loss without splitting into four blocks; whether it reports per-region numbers and a measured comparison is not confirmed. Reproducibility: unknown.
3. **Cogent Engineering (2024), core loss of an SRM from static finite element solutions, 6/4 case study** (https://www.tandfonline.com/doi/pdf/10.1080/23311916.2024.2322808, DOI 10.1080/23311916.2024.2322808; the publisher returned 403, full text not retrieved). The search summary says the loss is a sum of loss density times section weight, with stator loss concentrated in the yoke and rotor loss mostly in the rotor yoke; this disagrees with the tooth-dominated results of other studies, so it would test our per-region split sharply. Reproducibility: unknown; whether dimensions and a measured total are given is not confirmed.
4. **"Iron loss and temperature analysis of switched reluctance motor for electric vehicles", IET Electric Power Applications 14(11), 2020, pp. 2255-2262 (author list not confirmed; Yan is the first-listed name in the search result)** (https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/iet-epa.2020.0166; paywalled, abstract only). A four-phase 8/6 SRM; the iron loss model is fitted to the sheet data of the prototype, a 2D FEA gives the flux density waveforms, and a 2D thermal model is compared with a test platform. It matches the temperature rise, not a per-region loss table, per the abstract; the text notes tooth regions are alternating and yokes rotational. Reproducibility: low unless the full text gives dimensions and loss tables.

Also looked at, but not a per-region breakdown: Urgera 2024 (Newcastle thesis, section 3 above), a 12/8 SRM with measured iron loss obtained by subtraction (Table 8.6, p. 180): the measured iron loss is far above the commercial FEA prediction even with a build factor of 1.8 (for example 32.4 W measured against 2.57 W predicted at 150 rpm, 118 W against 21.13 W at 1600 rpm). It is a useful warning about the size of the measurement-versus-model gap, but it reports totals only. Dong C. Y. et al., "Iron loss analysis of switched reluctance motor", Electric Machines and Control 19(7), 2015, pp. 58-65 (12/8 SRM, yoke and pole of stator and rotor by time-stepping FEA; Chinese-language journal, full text not retrieved).

Owner pick: pending.

## Owner pick: per-region cross-check (2026-10-18)

Yan et al., IET Electr. Power Appl. 14(11), 2020, Table 3 (4-phase 8/6, 50W470, NNNN-SSSS): stator yoke 52.9 %, stator teeth 23.9 %, rotor 23.2 % of the iron loss. Compare region shares only; the paper's dimension labels are inconsistent, so absolute watts are not used.
