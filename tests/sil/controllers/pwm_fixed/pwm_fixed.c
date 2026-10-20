/* Test controller: phase 0 runs a fixed 25 % PWM duty, hard or soft chopped by the "soft" parameter. */
#include <string.h>

#include "srm_ctrl.h"
#include "srm_motor_tables.h"

static const srm_hal_t *hal;
static int soft = 0;

void ctrl_init(const srm_hal_t *h) { hal = h; }

int ctrl_param(const char *name, float value)
{
    if (strcmp(name, "soft") != 0) return -1;
    soft = value != 0.0f;
    return 0;
}

void ctrl_command(srm_cmd_mode_t mode, float value) { (void)mode; (void)value; }
void ctrl_isr(void) { hal->set_pwm(0, 0.25f, soft ? SRM_CHOP_SOFT : SRM_CHOP_HARD); }
void ctrl_slow(void) {}
