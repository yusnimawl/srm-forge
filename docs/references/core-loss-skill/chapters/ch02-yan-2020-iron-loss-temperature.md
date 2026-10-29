# Ch2: Yan et al. (2020) — Iron loss and temperature analysis of an SRM for EVs
*IET Electr. Power Appl. 14(11), 2119–2127 (journal page = PDF page + 2118); eq 1–8 and Table 1 verified against the page images, DOI 10.1049/iet-epa.2020.0166. 4-phase 8/6 SRM, 50W470, FE iron loss + thermal FE + measured winding temperature.*

## Core Idea
Fit **variable** Steinmetz coefficients to Epstein-frame data, apply them harmonic-by-harmonic to FE flux-density waveforms (radial and tangential components) block by block, then feed iron + copper loss into a 2D thermal FE model.

## Frameworks Introduced
- **Loss model** [eq 1, p2120]: P_fe = K_h·f·B_p^α + K_e·f²·B_p².
- **Variable-coefficient fit (50W470, 50–60 Hz dual-frequency method)**:
  - Constant fit from Fig 1 (eq 2, verified): P_fe = 0.0287·f·B_p^1.61 + 0.00027·f²·B_p², i.e. K_h = 0.0287, α = 1.61, K_e = 0.00027.
  - K_h ≈ 0.0287 (constant in practice).
  - K_e = [2.7 − ((f−50)/25) × 10⁻⁵]×10⁻⁴ (eq 3, p2121, verified; falls ~2×10⁻⁶ per +50 Hz); ~2.7×10⁻⁴ below 1.5 T, ~3.6×10⁻⁴ above 1.5 T.
  - α = 0.38B³ − 0.02B² − 0.33B + 1.44 (eq 4; independent of f at 1.3 T; rises with B).
  - Constant-coefficient fit (K_h 0.0287, α 1.61, K_e 0.00027) deviates more at high B and high f.
- **Harmonic iron loss** [eq 5–8, p2121]: B_m = √(B_Nm² + B_Tm²) (eq 6, radial + tangential harmonic m); P_fe,m = m·K_h·f·(B_Nm²+B_Tm²)^{α/2} + K_e·m²·f²·(B_Nm²+B_Tm²) (eq 7); eq 8 sums m = 1…n (9 harmonics in Table 2). Eq 5 is the same with K_e(m·f·B_m)².
- **Block method**: RY, RT, ST, and four stator-yoke segments (AB, BC, CD, DA) each get their own Fourier analysis; loss = specific loss × block mass.
- **Pole distribution effect**: NNNN–SSSS vs NNSN–SSNS windings (positive series). Rotor-yoke and stator-yoke waveforms change (tangential component roughly halves in the rotor yoke); stator/rotor tooth loss barely changes. Total 2.76 W vs 2.91 W (NNSN–SSNS is higher).
- **Thermal link**: 2D FLUX thermal model (27 773 nodes, 26 s), loads = iron loss + copper loss, boundaries 1st kind + 3rd kind (convection).

## Key Concepts
- Teeth see alternating magnetisation; yokes see rotational magnetisation → radial AND tangential B both matter.
- Epstein frame loss data are sinusoidal; SRM waveforms are not, hence harmonic decomposition.

## Machine (Table 1, p2122, labels as printed)
D1 = 110.0 mm "external radius of stator"; D2 = 98.0 "internal radius of stator"; D3 = 67.0 "external radius of air-gap"; d1 = 98.0 "internal radius of air-gap"; d2 = 43.0 "external radius of rotor"; d3 = 24.0 "internal radius of rotor"; b_s = 11.6 mm; b_r = 12.8 mm; T_ph = 40 turns; q = 4; N_r = 6; N_s = 8; steel 50ww470. The paper's labels are not self-consistent (D3 = 67 exceeds d2 = 43; D2 and d1 are both 98), so treat the geometry as indicative.

## Worked Example (8/6, NNNN–SSSS; Tables 2–4, p2123–2124)
Mass/loss split in W: RY 0.59 kg/0.32; RT 0.54 kg/0.32; ST 0.85 kg/0.66; stator yoke segments 0.29 kg each, 0.33 / 0.33 / 0.40 / 0.40. Stator = 76.8 % of iron loss (yoke 52.9 %, teeth 23.9 %), rotor 23.2 % (11.6 % each for rotor tooth and rotor yoke).

## Validation numbers
Winding temperature, simulation vs test (0.4 N·m): 500 rpm 31.0 vs 29.0 °C; 650 rpm 36.5 vs 35.0; 800 rpm 41.0 vs 40.0; 1000 rpm 45.0 vs 43.0. At 500 rpm: 0.3 N·m 29 vs 27 °C; 0.6 N·m 40 vs 39. Error ≤ 10 %, simulation conservative. Thermal data: 50W470 7700 kg/m³, k 22.6 W/m·K, cp 442 J/kg·K; copper k 401; varnish k 0.2; air k 0.026.

## Anti-patterns
- Constant Steinmetz coefficients over a wide f and B range.
- Treating the whole machine as one flux-density waveform; ignoring tangential B.

## Key Takeaways
1. Fit α(B) and K_e(f, B) separately; K_h can stay constant.
2. Include radial and tangential B in the harmonic sum.
3. Stator iron loss dominates (~77 %); put cooling and thermal work there.
4. Winding is the hottest part; the stator tooth is next; the rotor is coolest.

## Connects To
Ch3 (Li) cites this paper's coefficients model [13]. Ch1/Ch2 are both zone-sum methods.
