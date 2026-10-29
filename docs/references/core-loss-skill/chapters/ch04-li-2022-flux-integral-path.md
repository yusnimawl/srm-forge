# Ch4: Li et al. (2022) — Iron loss in SRM by the Flux Integral Path (FIP) method
*Progress In Electromagnetics Research M 112, 151–161 (printed page = PDF page + 150; eq 2, 10–13 and Tables 1–4 verified against the page images). 12/8 SRM, DW360-50, ANSYS Maxwell 2D FEA as reference.*

## Core Idea
Instead of four blocks (stator pole/yoke, rotor pole/yoke), treat the whole machine as **12 × the flux path of one excited stator pole**, and drive eddy and hysteresis loss from the **time integral** (and slope segments) of the stator-pole B(t) from FEA.

## Frameworks Introduced
- **Flux path length L** of one excited pole (eq 2, p154, as printed): L = π/N_S + β·d_s + π/N_R + γ·D_r + D_s − d_r, with D_s, d_s stator outer and inner diameter, D_r, d_r rotor outer and inner diameter, β, γ stator and rotor pole arc coefficients; air gap ignored. As written the terms mix dimensionless and length terms (and the paper's text names both stator diameters "D_S and d_S"), so treat eq 2 as an empirical length scale and recalibrate C_e, C_h rather than trusting its units. Total path = 12·L for a 12/8 (three phases × four poles).
- **Flux flow** Q = a·c·(1/T)∫B(t)dt (stator pole arc a × stack length c).
- **Eddy**: P_e = 12L·C_e·f²·Q.
- **Hysteresis** (piecewise-linear fit of B(t) around extrema): P_h = 12L·C_h·f·Σ_k p_k·(1/T_k)∫B_k dt, p_k = segment slope dB/dt, T_k its duration.
- **Total**: P_iron = P_e + P_h. Coefficients C_e = 0.58, C_h = 1.2 were fitted to measured/FEA loss for this machine (not universal).
- **Baselines** compared: loss-separation P = K_e f² B_p² + K_h f B_p^α (K_e 1e-4, K_h 0.034, α 1.5, valid 100–500 Hz); FFT method summing the first 8 harmonics, B_m = √(B_rm² + B_tm²); dual-frequency method P/f = K_e a(B) f + K_h b(B).

## Machine (Table 1, p158, verified)
Stator OD 120 mm, ID 69.8 mm; 12 stator / 8 rotor poles; 50 turns per pole; rotor OD 69 mm, ID 30 mm; stator pole embrace 0.5, rotor pole embrace 0.355; stator yoke 9 mm, rotor yoke 6.7 mm; stack 65 mm; DW360-50.

## Table 2 caveat (p159)
The FFT columns and two other cells are printed without decimal points (FFT eddy 1297, 3503, 6253, 10162; FFT hysteresis 1755, 2824, 3786, 4772; separation hysteresis 4525 at 500 Hz). Reading them as 12.97, 35.03, 62.53, 101.62, 17.55, 28.24, 37.86, 47.72, 45.25 W reproduces the Table 3 totals at 200–400 Hz. At 500 Hz the components sum to 149.34 W (FFT) and 158.25 W (FIP) against Table 3's 148.34 and 159.25 W, a ~1 W inconsistency in the paper; use Table 3.

## Results (loss in W; FEA ref; Table 3)
Frequency 100 / 200 / 300 / 400 / 500 Hz → FEA 8.25 / 31.02 / 66.81 / 108.03 / 157.47.
Separation error 11.15 / 5.16 / 7.74 / 10.72 / 10.08 %. FFT error 5.82 / 1.61 / 5.30 / 7.07 / 5.80 %. FIP error 11.39 / 2.77 / 3.86 / 2.89 / 1.13 %. So FIP is *worse* at 100 Hz and best at ≥200 Hz. Compute time: FEA 375 s, separation 103 s, FFT 542 s, FIP 261 s. At 500 Hz FIP over-predicts FEA because local saturation removes loss in FEA. Hysteresis dominates at low frequency, eddy above ~200–300 Hz.

## Anti-patterns
- Peak-B only Steinmetz on non-sinusoidal flux.
- FIP's coefficients are fitted to this machine; its dimensional consistency is loose (L, Q, C_e mix units) — use as an empirical model, recalibrate per machine, and don't read it as first-principles.

## Key Takeaways
1. A single flux-path/flux-flow figure can replace four-block bookkeeping, at the cost of calibrating C_e, C_h.
2. Validate against FEA over the operating frequency range; check the low-frequency end.
3. Saturation (iron with no loss) makes simple models over-predict at high frequency.

## Connects To
Ch2 (Yan) for K_e/K_h/α baselines; Ch3 for the same FFT-vs-other comparison idea.
