/* Test controller: each phase conducts (both switches on) while its own rotor angle is in [theta_on, theta_off). */
#include <math.h>
#include <string.h>

#include "srm_ctrl.h"
#include "srm_motor_tables.h"

static const srm_hal_t *hal;
static double theta_on = 0.0, theta_off = 0.0;

void ctrl_init(const srm_hal_t *h) { hal = h; }

int ctrl_param(const char *name, float value)
{
    if (strcmp(name, "theta_on") == 0) theta_on = value;
    else if (strcmp(name, "theta_off") == 0) theta_off = value;
    else return -1;
    return 0;
}

void ctrl_command(srm_cmd_mode_t mode, float value) { (void)mode; (void)value; }

void ctrl_isr(void)
{
    const double two_pi = 6.283185307179586;
    const double pitch = SRM_POLE_PITCH_RAD;
    double theta = two_pi * (double)hal->encoder_count() / (double)hal->encoder_cpr;
    for (uint8_t k = 0; k < hal->n_phases; k++) {
        double p = fmod(theta - (double)k * pitch / (double)hal->n_phases, pitch);
        if (p < 0.0) p += pitch;
        bool on = p >= theta_on && p < theta_off;
        hal->set_switches(k, on, on);
    }
}

void ctrl_slow(void) {}
