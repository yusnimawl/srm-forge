---
name: srm-core-loss
description: "Knowledge base from 4 SRM core/iron-loss papers: Torrent 2010 (zone method with hysteresis, eddy and excess terms), Yan 2020 (variable Steinmetz coefficients, harmonic iron loss, thermal FE), Li 2022 (Flux Integral Path method), Melo 2024 (static FEMM time-harmonic vs B-harmonic). Use when estimating SRM iron/core loss, choosing a loss model, fitting Steinmetz coefficients, or linking iron loss to temperature. Companion to krishnan-srm-drives."
---

<!-- argument-hint: [method name, paper, or chapter number] -->

# SRM Core / Iron Loss — 4 Papers
**Papers**: 4 | **Chapters**: 4 | **Generated**: 2026-10-18 | Companion to `krishnan-srm-drives` (Materu–Krishnan zone method is the ancestor of all four).

## How to Use
Ask by topic (`eddy loss`, `excess`, `FIP`, `FEMM`, `variable K_e`) or `ch02`. Chapter files hold equations, coefficients and numbers. Equations and tables flagged as garbled in the first extraction were re-checked against the PDF page images; page refs are in each chapter header (see the 'Verification' note below).

## Core Frameworks
- **Zone-sum method (Torrent 2010; Yan 2020; Melo Method 1)**: split the machine into stator pole, stator yoke (several segments), rotor pole, rotor yoke. Get B(t) per zone (derived from stator-pole B(t) by sums/differences, or from FE). Loss = Σ specific loss × zone mass.
- **Three-term loss (Torrent)**: hysteresis (loop area × f / density), classical eddy k·⟨(dB/dt)²⟩, excess k·⟨|dB/dt|^1.5⟩. Needs dB/dt, not just B_peak.
- **Two-term Steinmetz with harmonics (Yan, Melo M1, Li baseline)**: P = K_h·f·B^α + K_e·f²·B². Apply per Fourier harmonic m of B(t) with B_m = √(B_radial² + B_tangential²). Use **variable** coefficients (Yan: K_h≈0.0287, α(B) cubic, K_e falling with f and rising above 1.5 T) when f or B range is wide.
- **Flux Integral Path (Li 2022)**: P_e = 12L·C_e·f²·Q, P_h = 12L·C_h·f·Σ p_k·mean(B_k); coefficients fitted per machine. Better than separation/FFT at ≥200 Hz in the paper, worse at 100 Hz.
- **Static time-harmonic FE (Melo 2024)**: current harmonics → FEMM at 45 positions → average; includes skin effect and saturation via θ_h scaling; θ_h,max (20°) is the knob. Disagrees with B-harmonic methods by 0.4–3×; authors say no reference exists.
- **Thermal chain (Yan 2020)**: iron loss + copper loss → 2D thermal FE; ≤10 % error to measured winding temperature; stator = 77 % of iron loss; winding hottest.

## Chapter Index
| # | Title | Key frameworks |
|---|---|---|
| [ch01](chapters/ch01-torrent-2010-zone-method.md) | Torrent 2010 | zones, hysteresis + eddy + excess, Leplus loop |
| [ch02](chapters/ch02-yan-2020-iron-loss-temperature.md) | Yan 2020 | variable K_e, α(B), harmonic loss, pole distribution, thermal |
| [ch03](chapters/ch03-melo-2024-static-fe-femm.md) | Melo 2024 | static FEMM, complex μ, θ_h, B_harm vs FEMM |
| [ch04](chapters/ch04-li-2022-flux-integral-path.md) | Li 2022 | FIP, flux flow, piecewise-linear hysteresis |

## Topic Index
- **Dual-frequency method** → ch02, ch04
- **dB/dt, excess loss** → ch01
- **Eddy-current coefficient** → ch01, ch02, ch04
- **Flux path / flux flow** → ch04
- **Harmonic (Fourier) loss** → ch02, ch03, ch04
- **Hysteresis angle θ_h** → ch03
- **Leplus hysteresis loop** → ch01
- **Lamination skin effect** → ch03
- **Measured core loss (P_fe = P_total − P_cu − P_mech)** → ch01
- **Radial + tangential B** → ch02, ch04
- **Steinmetz α(B)** → ch02
- **Thermal model** → ch02
- **Zone frequencies** → ch01

## Supporting Files
[glossary.md](glossary.md) · [patterns.md](patterns.md) · [cheatsheet.md](cheatsheet.md)

## Verification
Docling (technical mode) was used for the text but left the equations undecoded, so the flagged items were read from rendered PDF pages: Torrent Table I and eq 13–14; Yan eq 2–4, 5–8 and Table 1; Li eq 2, Table 1 and Table 2. Results: Torrent Table I confirmed as f_base, f_base×m, f_base, f_base/Nr, f_base/Nr; Yan eq 2 confirmed (K_h 0.0287, α 1.61, K_e 0.00027); Li Table 1 has 50 turns per pole (the first extraction said 69); Li Table 2's FFT columns lack decimal points in the paper itself.

## Scope & Limits
Summaries of 4 papers only; coefficients are machine- and steel-specific (50W470, M45G29, FeV 600-50 HA, DW360-50). Only Torrent and Yan have measurements; Li and Melo are FE-vs-model.
