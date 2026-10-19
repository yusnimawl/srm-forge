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
