/* Test controller: phase A has both switches on from the start, the other phases stay off. */
#include "srm_ctrl.h"
#include "srm_motor_tables.h"

void ctrl_init(const srm_hal_t *hal)
{
    for (uint8_t k = 0; k < hal->n_phases; k++) hal->set_switches(k, k == 0, k == 0);
}

int ctrl_param(const char *name, float value) { (void)name; (void)value; return -1; }
void ctrl_command(srm_cmd_mode_t mode, float value) { (void)mode; (void)value; }
void ctrl_isr(void) {}
void ctrl_slow(void) {}
