# Ch1: Torrent et al. (2010) — Method for estimating core losses in SRMs
*Euro. Trans. Electr. Power 2010, DOI 10.1002/etep.475. 6/4 SRM, measured validation. Page refs are PDF pages (journal pages are unnumbered in the PDF); equations and Table I verified against the page images.*

## Core Idea
Run a transient SRM simulation (nonlinear ψ(θ,i) model + converter + control), take the stator-pole B(t), derive B(t) in every other zone from it, then compute **specific** loss (W/kg) per zone as hysteresis + classical eddy + excess from B and dB/dt, and sum × zone mass.

## Frameworks Introduced
- **Zone decomposition (6/4: 9 zones, 5 distinct)** [PDF p4, eq 8–9, Fig 3]: stator poles (1,1',1''), stator yoke (2; 3,3'), rotor poles (4,4'), rotor yoke (5).
  - Stator pole B(t): ~unipolar triangular pulse, same for every phase, shifted by ε = 2π/(m·Nr).
  - Stator yoke B = sums of stator-pole waveforms. Rotor pole B is **bipolar** (flips every half revolution). Rotor yoke = difference of rotor-pole waveforms.
- **Zone frequencies** [Table I, PDF p5; verified] (f_base = n·Nr/60, eq 9; ε = 2π/(m·Nr), eq 8): zones 1,1',1'' (stator poles) f_base; zone 2 (stator yoke) f_base × m; zones 3,3' (stator yoke) f_base; zones 4,4' (rotor poles) f_base/Nr; zone 5 (rotor yoke) f_base/Nr.
- **Three-term loss, per zone (W/kg)** [eq 10–17, PDF p5–6]: P_core = Σ (P_hys,i + P_eddy,i + P_exc,i)·G_i.
  - Hysteresis: P_hys = S·f/δ (eq 11), S = area of the local B–H loop, δ = density (kg/m³). Loop from the Leplus 5-section polynomial model (Appendix), one loop per zone.
  - Classical eddy: P_eddy = k_eddy·⟨(dB/dt)²⟩ = k_eddy·(dB/dt)²_rms, with k_eddy = e²/(4·k_cir·ρ_fe·δ) (eq 14, verified; δ = mass density, e = sheet thickness); the classical eq 13 is e²/(12·ρ_fe·δ). k_cir (1 < k_cir < 3) accounts for inner lamination paths seeing smaller emf. Note the paper writes density as δ, not d.
  - Excess (Fiorillo–Novikov): P_exc = k_exc·⟨|dB/dt|^{3/2}⟩ = k_exc·(|dB/dt|^{3/2})_rms; k_exc fitted from measured loss vs B and f.
- **Magnetisation fit**: ψ(θ,i)=p0+Σ_{n=1..5} p_n cos(n·Nr·θ), with p_n = p_n1 i³ + p_n2 i² + p_n3 i.

## Key Concepts
- **Specific loss**: W/kg per zone; total needs zone masses from geometry × density.
- **Control dependence**: single-pulse vs constant-current give different dB/dt, so the same machine/speed has different core loss.
- **Measured loss split**: P_fe = P_total − P_copper − P_mech (mech loss from a DC-machine coupling test).

## Anti-patterns
- Using one peak-B Steinmetz number for a non-sinusoidal, zone-dependent waveform.
- Ignoring control mode: under single-pulse control losses stay ~flat with speed; under constant-current they rise ~proportionally with speed.

## Reference data (6/4, 750 W, 300 V, 3000 rpm base)
Stator OD 125.1 mm, ID 61 mm, stack 61 mm, air gap 0.30 mm. Steel FeV 600-50 HA: 0.5 mm, 7800 kg/m³, ρ = 40×10⁻⁸ Ω·m.
Results: hysteresis largest in rotor zones 4,5; eddy largest in stator yoke zone 3. Calculated core loss is slightly **below** measured (stray load loss and rotational loss not modelled).

## Key Takeaways
1. Zone B(t) can be derived from stator-pole B(t) by sums/differences — no FE transient needed.
2. dB/dt (not just B_peak) drives eddy and excess loss.
3. Model under-predicts measured loss slightly; budget a rotational/stray allowance.
4. Loss depends on control strategy; always state it.

## Connects To
- Ch2 (Melo): same zone-sum idea, Fourier version. Ch4 (Li): lumps zones into one flux path.
- Krishnan skill: Materu & Krishnan 1992 loss estimation (the ancestor of this method).
