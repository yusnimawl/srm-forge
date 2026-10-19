/* PWM current controller. Each phase has a PI current loop on i_ref, the current that gives the commanded
 * torque at the centre of the conduction window [theta_on, theta_off). The PI output is a voltage, applied
 * as a soft-chopping duty = v_ref / vbus. Outside the window the phase is off and its integrator is reset. */
#include "srm_ctrl.h"
#include "srm_motor_tables.h"
#include "srm_ref.h"

static const srm_hal_t *hal;
static float kp = 0.0f;     /* V/A; 0 = derived from f_bw */
static float ki = 0.0f;     /* V/(A*s); 0 = derived from f_bw */
static float f_bw = 0.0f;   /* Hz; 0 = pwm_hz / 20 */
static float integ[SRM_N_PHASES];   /* V */
static float dt;

static const srm_ref_param_t own[] = {
    {"kp", &kp},
    {"ki", &ki},
    {"f_bw", &f_bw},
};

int ctrl_param(const char *name, float value)
{
    return srm_ref_param(own, (int)(sizeof own / sizeof own[0]), name, value);
}

void ctrl_init(const srm_hal_t *h)
{
    hal = h;
    srm_ref_init(h);
    dt = srm_ref_ok() ? 1.0f / h->isr_hz : 0.0f;
    srm_ref_pi_gains(h, f_bw, &kp, &ki);
    for (int k = 0; k < SRM_N_PHASES; k++) integ[k] = 0.0f;
}

void ctrl_command(srm_cmd_mode_t mode, float value) { srm_ref_command(mode, value); }

void ctrl_slow(void) { srm_ref_slow(); }

void ctrl_isr(void)
{
    if (!srm_ref_ok()) {
        for (uint8_t k = 0; k < hal->n_phases; k++) hal->set_switches(k, false, false);
        return;
    }
    float theta = srm_ref_angle(hal);
    float i_ref = srm_ref_i_ref();
    float vbus = hal->vbus_volts();
    if (!(vbus > 1.0f)) vbus = 1.0f;
    for (uint8_t k = 0; k < hal->n_phases && k < SRM_N_PHASES; k++) {
        if (!srm_ref_in_window(srm_ref_phase_angle(theta, k)) || i_ref <= 0.0f) {
            integ[k] = 0.0f;
            hal->set_switches(k, false, false);
            continue;
        }
        float duty = srm_ref_pi_duty(&integ[k], i_ref - srm_ref_current(hal, k), kp, ki, dt, vbus);
        hal->set_pwm(k, duty, SRM_CHOP_SOFT);
    }
}
