# Patterns

## Zone-sum core loss
**When to use**: design stage, you have or can derive B(t) per zone.
**How**: stator-pole B(t) → yoke by phase sums, rotor pole by shifted copies (bipolar), rotor yoke by differences → per-zone loss → × mass.
**Trade-offs**: ignores rotational and minor-loop loss; under-predicts measurement slightly (Ch 1).

## Harmonic Steinmetz with radial + tangential B
**When to use**: FE gives B_r, B_t vs time at points/blocks.
**How**: FFT; B_m = √(B_r,m² + B_t,m²); P_m = m·K_h·f·B_m^α + K_e·(mf)²·B_m²; sum ~8–9 harmonics; mass-weight.
**Trade-offs**: superposition is approximate for nonlinear iron.

## Variable-coefficient fit
**When to use**: wide f (50 → 500+ Hz) and B (to saturation).
**How**: dual-frequency method on Epstein data at pairs of frequencies; hold K_h fixed, fit K_e(f), K_e(B) in sections, α(B) polynomial.

## Piecewise-linear dB/dt
**When to use**: unipolar triangular stator-pole B(t).
**How**: break the cycle at extrema, linear fit each segment, constant slope p_k, then evaluate dB/dt-based terms analytically (Ch 4, and trivially for eddy/excess in Ch 1).

## Static time-harmonic FE
**When to use**: only a static FE tool (FEMM) is available.
**How**: current harmonics → solve at 45 positions per 90° (6/4) → average → sum harmonics. Tune θ_h,max.

## Measured core loss
**How**: P_fe = P_total − P_copper(at operating temperature) − P_mechanical (DC-machine coupling test).
