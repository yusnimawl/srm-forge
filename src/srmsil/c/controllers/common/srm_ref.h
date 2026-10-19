/* Shared parts of the reference controllers: rotor angle, phase current, conduction window, torque
 * command and speed loop, and the parameter lookup. State is file-static (one controller per image). */
#ifndef SRM_REF_H
#define SRM_REF_H

#include <stdbool.h>
#include <stdint.h>

#include "srm_ctrl.h"

/* One tunable value reachable by name from ctrl_param. */
typedef struct {
    const char *name;
    float *value;
} srm_ref_param_t;

/* Look `name` up in the controller's own table, then in the shared one (theta_on, theta_off, speed_kp,
 * speed_ki, speed_filter_hz, torque_limit, resolver_pole_pairs). 0 = accepted, -1 = unknown name. */
int srm_ref_param(const srm_ref_param_t *own, int n_own, const char *name, float value);

/* Call from ctrl_init (after the parameters were set) and from ctrl_command / ctrl_slow. */
void srm_ref_init(const srm_hal_t *hal);
void srm_ref_command(srm_cmd_mode_t mode, float value);
void srm_ref_slow(void);   /* speed estimate and speed PI; call at 1 kHz */

/* Mechanical rotor angle in [0, 2*pi): from the encoder, or from the resolver when encoder_cpr == 0. */
float srm_ref_angle(const srm_hal_t *hal);
/* theta - k * SRM_STROKE_RAD wrapped into [0, SRM_POLE_PITCH_RAD): phase k's own angle, aligned at 0. */
float srm_ref_phase_angle(float theta, uint8_t k);
/* Electrical degrees from the unaligned position (0 = unaligned, 180 = aligned) of a phase angle. */
float srm_ref_el_deg(float theta_phase);
/* True while the phase angle lies in [theta_on, theta_off). */
bool srm_ref_in_window(float theta_phase);

/* Phase current in amperes from the ADC code and the nominal scale. */
float srm_ref_current(const srm_hal_t *hal, uint8_t k);

float srm_ref_speed(void);        /* filtered speed estimate, rad/s */
float srm_ref_torque_cmd(void);   /* torque command in [0, torque_limit], N*m */
float srm_ref_i_ref(void);        /* current for the torque command at the window centre, A */

#endif
