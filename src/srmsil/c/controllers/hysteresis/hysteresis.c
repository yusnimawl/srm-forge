/* Hysteresis current controller. Each phase is excited inside its conduction window [theta_on, theta_off)
 * and held within +-band/2 of i_ref, the current that gives the commanded torque at the window centre.
 * Soft chopping keeps the lower switch on and toggles the upper; hard chopping toggles both. Intended ISR
 * rate: 50 kHz (set isr_hz in the scenario). */
#include "srm_ctrl.h"
#include "srm_motor_tables.h"
#include "srm_ref.h"

static const srm_hal_t *hal;
static float band = 0.05f * SRM_I_MAX_A;   /* A */
static float soft = 1.0f;                  /* 1 = soft chopping, 0 = hard */
static bool on[SRM_N_PHASES];              /* per-phase switching state while in the window */

static const srm_ref_param_t own[] = {
    {"band", &band},
    {"soft", &soft},
};

int ctrl_param(const char *name, float value)
{
    return srm_ref_param(own, (int)(sizeof own / sizeof own[0]), name, value);
}

void ctrl_init(const srm_hal_t *h)
{
    hal = h;
    srm_ref_init(h);
    for (int k = 0; k < SRM_N_PHASES; k++) on[k] = true;
}

void ctrl_command(srm_cmd_mode_t mode, float value) { srm_ref_command(mode, value); }

void ctrl_slow(void) { srm_ref_slow(); }

void ctrl_isr(void)
{
    float theta = srm_ref_angle(hal);
    float i_ref = srm_ref_i_ref();
    for (uint8_t k = 0; k < hal->n_phases && k < SRM_N_PHASES; k++) {
        if (!srm_ref_in_window(srm_ref_phase_angle(theta, k)) || i_ref <= 0.0f) {
            on[k] = true;   /* a window starts with the phase switched on */
            hal->set_switches(k, false, false);
            continue;
        }
        float i = srm_ref_current(hal, k);
        if (i < i_ref - 0.5f * band) on[k] = true;
        else if (i > i_ref + 0.5f * band) on[k] = false;
        hal->set_switches(k, on[k], on[k] || soft != 0.0f);
    }
}
