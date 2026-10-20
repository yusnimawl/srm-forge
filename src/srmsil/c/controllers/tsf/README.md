# Torque sharing function controller

Each phase gets a share s of the torque command from its electrical angle (degrees from the unaligned
position, 0 = unaligned, 180 = aligned). With stroke = 360 / phases the share rises as s(x) = 3x^2 - 2x^3 over
[`theta_on`, `theta_on` + `overlap`], is 1 until `theta_on` + stroke, falls over the next `overlap` degrees
and is 0 elsewhere (the window may wrap through 0/360; `overlap` is limited to one stroke). The shares of
neighbouring phases sum to 1. Phase k gets `i_ref` = `srm_i_of_t(phase angle, s * torque command)` and a PI
current loop like `pwm_current` (soft-chopping duty = v_ref / vbus, integrator limited to 0..vbus); a phase
with no share is off and its integrator is reset. A speed command goes through a PI loop on the speed
estimate that produces the torque command. Intended `pwm_hz`: 20 kHz.

`kp` and `ki` of 0 mean "derive from `f_bw`": kp = L_min * 2*pi*f_bw, ki = R * 2*pi*f_bw. `f_bw` of 0 means
`pwm_hz` / 20.

| Parameter | Unit | Default |
|---|---|---|
| `theta_on` | electrical deg from unaligned | 15 |
| `overlap` | electrical deg | 30 |
| `kp` | V/A | 0 (SRM_L_MIN_H * 2*pi*f_bw) |
| `ki` | V/(A*s) | 0 (SRM_R_OHM * 2*pi*f_bw) |
| `f_bw` | Hz | 0 (pwm_hz / 20) |
| `speed_kp` | N*m/(rad/s) | 0.05 |
| `speed_ki` | N*m/rad | 0.5 |
| `speed_filter_hz` | Hz | 50 |
| `torque_limit` | N*m | SRM_T_MAX_NM |
| `resolver_pole_pairs` | - | 1 |

Every parameter can also be changed while the controller runs (`ctrl_param` returns 0 and the new value is used from the next ISR); `resolver_pole_pairs` is the exception and returns -2 after `ctrl_init`.

## Notes

- Speed loop gains: see the `pwm_current` README.
- The torque table returns 0 where a phase cannot make positive torque; at high speed the bus may not build
  the current an overlap needs, and the torque then dips in the hand-over.
- `resolver_pole_pairs` must divide the rotor pole count; otherwise (or with `isr_hz` <= 0) every switch stays off.

Firmware note: the generated `srm_motor_tables.h` defines its i(theta, T) table `static const` per translation unit (about 46 KB each); include it in one .c file or switch to an extern definition.
