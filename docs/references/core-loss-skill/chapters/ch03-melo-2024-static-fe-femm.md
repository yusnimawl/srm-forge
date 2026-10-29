# Ch3: Melo & Araújo (2024) — SRM core loss with a static finite-element method
*Cogent Engineering 11:1, 2322808 (printed page = PDF page − 1; eq 5 and 6 verified against the page images). 6/4 SRM, M45G29 lamination, FEMM. Simulation-only comparison, no experiment.*

## Core Idea
Use **phase-current harmonics** (not flux harmonics) as the input to a time-harmonic FEMM solve at a series of static rotor positions. FEMM then gives loss with lamination skin effect, saturation and a complex-permeability hysteresis model coupled, per harmonic. Compare against the classic "B_harm" Fourier-of-flux-density Steinmetz method.

## Frameworks Introduced
- **Method 1 "B_harm"** (equivalent-circuit model + Fourier of B per section + Steinmetz): P_core = P_h + P_e = k_h·f·B_max^(a+b·B_max) + k_e·(f·B_max)² (eq 5, p5; excess term dropped for a fair comparison); P_SRM = Σ P_core,k·W_k over sections (6 stator pole, 2 yoke-1, 4 yoke-2, 4 rotor pole, 4 rotor yoke instances).
  - Stator-pole B shifted by the stroke angle θ_S = 2π(1/Nr − 1/Ns) (eq 6, p6, verified; = 30° for 6/4). Yoke-1 = sum of 3 phase poles, yoke-2 = two summed minus one, rotor pole/yoke as in Ch1.
  - M45G29 fit (k_h, a, b, k_e): f<150 Hz: 5.1e-3, 1, 0.71031, 7.864e-5; 150–600 Hz: k_e 5.864e-5; >600 Hz: k_h 3.1e-3, b 0.51031, k_e 4.864e-5.
- **Method 2 "FEMM"** (steps): (1) decompose phase current into harmonics; (2) for each harmonic h, solve time-harmonic FEMM at k_max = 45 rotor positions (Δθ = 2° over a 90° mech. current period); (3) average loss over positions → p_core,h; (4) total = Σ over harmonics. Single-phase analysis only (other phases demagnetised).
- **1-D lamination model** (semi-infinite, thickness 2b): H(y)=H_s cosh(αy)/cosh(αb), α=(1+j)/δ, δ=√(2/(ωσμ)). Eddy loss per unit surface P_eddy,s ∝ (H_s²/(σδ))·[sinh(2b/δ) − sin(2b/δ)]/[cosh(2b/δ) + cos(2b/δ)].
- **Hysteresis as an elliptical loop**: complex permeability μ_h = |μ_h|e^{−jθ_h}; θ_h is the lag angle; coupled with eddy via μ → μ_h in the diffusion equation. Volumetric hysteresis loss P_h,vol = ½·ω·|B_max|²/|μ_h|·sin θ_h ≈ ½ω·B_max²/|μ_h|·θ_h; θ_h scales with saturation: θ_h = θ_h,max·|μ_h|/|μ_h,max|.
- **θ_h,max** is the main tuning knob: fixed to 20° (O'Kelly: ~30° below the knee, <20° at high B). Results scale with it.

## Anti-patterns / limitations (as stated)
- Superposition of harmonic losses is only valid for linear systems; SRM is strongly nonlinear.
- Method 2 ignores minor loops, rotational loss, phase overlap (always a single-phase analysis) and treats pulsating/rotating hysteresis alike.
- FEMM is limited to sinusoidal time-harmonic problems.
- **The authors state neither method can be taken as a reference**; experimental or transient FE validation is the next step.

## Key results (6/4: 750 W, 1800 rpm, 150 V, 0.4 mm gap, 0.36 mm M45G29, Rs 1.3 Ω)
Ratio FEMM / B_harm total core loss: light load (≈1.4 N·m) 0.44 at 688 rpm → 1.23 at 3625 rpm; 2.9 N·m 0.79 → 1.97; 6.2 N·m 2.5 → 3.1 (always >1 and rising with load and speed). Convergence only for ~700–1100 rpm (2.9 N·m) and ~3000–3300 rpm (1.4 N·m). Hysteresis dominates at low speed, eddy at high speed; the crossover speed falls as load rises (saturation lowers θ_h).

## Key Takeaways
1. Methods that assume uniform B disagree with skin-effect-aware FE by factors 0.4–3 across the load–speed plane; do not trust either blindly.
2. Report which method and which θ_h/fit parameters were used.
3. Loss split: hysteresis ≫ eddy at low speed; reverses at higher speed.

## Connects To
Ch1 (zone Fourier), Ch2 (variable coefficients), Ch4 (Li, FIP, uses FFT/loss-separation baselines).
