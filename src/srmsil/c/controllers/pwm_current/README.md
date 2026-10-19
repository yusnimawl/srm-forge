# PWM current controller

Each phase has a PI current loop inside its window [`theta_on`, `theta_off`) (electrical degrees from the
unaligned position, 0 = unaligned, 180 = aligned) on `i_ref`, which is `srm_i_of_t(window centre, torque
command)`. The PI output is a voltage; the soft-chopping duty is clamp(v_ref / vbus, 0, 1), and the integrator
is limited to 0..vbus. Outside the window the phase is off and the integrator is reset. A speed command
goes through a PI loop on the speed estimate that produces the torque command.

`kp` and `ki` of 0 mean "derive from `f_bw`": kp = L_min * 2*pi*f_bw, ki = R * 2*pi*f_bw. `f_bw` of 0 means
`pwm_hz` / 20.

| Parameter | Unit | Default |
|---|---|---|
| `kp` | V/A | 0 (SRM_L_MIN_H * 2*pi*f_bw) |
| `ki` | V/(A*s) | 0 (SRM_R_OHM * 2*pi*f_bw) |
| `f_bw` | Hz | 0 (pwm_hz / 20) |
| `theta_on` | electrical deg from unaligned | 0 |
| `theta_off` | electrical deg from unaligned | 150 |
| `speed_kp` | N*m/(rad/s) | 0.05 |
| `speed_ki` | N*m/rad | 0.5 |
| `speed_filter_hz` | Hz | 50 |
| `torque_limit` | N*m | SRM_T_MAX_NM |
| `resolver_pole_pairs` | - | 1 |
