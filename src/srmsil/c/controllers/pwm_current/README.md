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

Live changes (`ctrl_param` while the controller runs, in the SIL with a parameter step and on the HIL with Set parameter): `kp`, `ki`, `f_bw`, `theta_on`, `theta_off`, `speed_kp`, `speed_ki`, `speed_filter_hz` and `torque_limit` return 0 and the new value is used from the next ISR. `resolver_pole_pairs` returns -2 once `ctrl_init` has run (it sets the angle range), so set it before the run; a name the controller does not have returns -1. On the HIL the controller board's serial link also refuses a name over 23 bytes and a value that is not finite.

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

Firmware note: the generated `srm_motor_tables.h` defines its i(theta, T) table `static const` per translation unit (about 46 KB each); include it in one .c file or switch to an extern definition.
