# Hysteresis current controller

Each phase conducts inside its window [`theta_on`, `theta_off`) (electrical degrees from the unaligned
position, so 0 = unaligned and 180 = aligned) and its current is held within +-`band`/2 of `i_ref`. `i_ref` is
`srm_i_of_t(window centre, torque command)`. A torque command is used directly; a speed command goes through
a PI loop on the speed estimate (from encoder angle differences at 1 kHz) that produces the torque command.

Soft chopping (`soft` = 1) keeps the lower switch on and toggles the upper; hard chopping toggles both.
The intended ISR rate is 50 kHz: set `isr_hz` = 50000 in the scenario. The current can overshoot the band by
the rise during one ISR period plus the compute delay.

| Parameter | Unit | Default |
|---|---|---|
| `band` | A | 0.05 * SRM_I_MAX_A |
| `soft` | 1 = soft, 0 = hard | 1 |
| `theta_on` | electrical deg from unaligned | 0 |
| `theta_off` | electrical deg from unaligned | 150 |
| `speed_kp` | N*m/(rad/s) | 0.05 |
| `speed_ki` | N*m/rad | 0.5 |
| `speed_filter_hz` | Hz | 50 |
| `torque_limit` | N*m | SRM_T_MAX_NM |
| `resolver_pole_pairs` | - | 1 |

## Notes

- The window may wrap through 0/360 degrees: `theta_on` = -15 starts conduction 15 degrees before the unaligned
  position (angles are normalised modulo 360; `i_ref` is taken at the window centre).
- Speed loop gains: the defaults (`speed_kp` 0.05, `speed_ki` 0.5, `speed_filter_hz` 50) suit an inertia of about
  1e-3 kg*m^2 (crossover about 50 rad/s, below the 314 rad/s filter pole). For another inertia J choose a
  crossover w_c (rad/s; keep it below about 1/20 of the filter pole 2*pi*`speed_filter_hz` and below 1/10 of the
  1 kHz loop rate) and set `speed_kp` = J * w_c, `speed_ki` = `speed_kp` * w_c / 16. Example: J = 1e-4, w_c = 100:
  `speed_kp` 0.01, `speed_ki` 0.0625, `speed_filter_hz` 500. The controllers only motor (torque >= 0), so a speed
  overshoot is not braked.
- `resolver_pole_pairs` must divide the rotor pole count; otherwise (or with `isr_hz` <= 0) every switch stays off.
