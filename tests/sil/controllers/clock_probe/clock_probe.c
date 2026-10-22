/* Test controller for the controller clock: phase 0's upper switch toggles on every ctrl_isr, phase 1's on every
   ctrl_slow, phase 2's is bit 0 of micros() / 100, and phase 3's is on while hal->pwm_hz and hal->isr_hz equal the
   "pwm_hz" and "isr_hz" parameters. The lower switches stay off. */
#include <string.h>

#include "srm_ctrl.h"
#include "srm_motor_tables.h"

static const srm_hal_t *hal;
static bool isr_on, slow_on;
static float want_pwm, want_isr;

void ctrl_init(const srm_hal_t *h) { hal = h; }

int ctrl_param(const char *name, float value)
{
    if (strcmp(name, "pwm_hz") == 0) want_pwm = value;
    else if (strcmp(name, "isr_hz") == 0) want_isr = value;
    else return -1;
    return 0;
}

void ctrl_command(srm_cmd_mode_t mode, float value) { (void)mode; (void)value; }

void ctrl_isr(void)
{
    isr_on = !isr_on;
    hal->set_switches(0, isr_on, false);
    hal->set_switches(2, (hal->micros() / 100u) & 1u, false);
    hal->set_switches(3, hal->pwm_hz == want_pwm && hal->isr_hz == want_isr, false);
}

void ctrl_slow(void)
{
    slow_on = !slow_on;
    hal->set_switches(1, slow_on, false);
}
