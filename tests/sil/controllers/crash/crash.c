/* Test controller: writes through a null pointer in ctrl_isr. */
#include "srm_ctrl.h"
#include "srm_motor_tables.h"

void ctrl_init(const srm_hal_t *h) { (void)h; }
int ctrl_param(const char *name, float value) { (void)name; (void)value; return 0; }
void ctrl_command(srm_cmd_mode_t mode, float value) { (void)mode; (void)value; }
void ctrl_slow(void) {}
void ctrl_isr(void) { *(volatile int *)0 = 1; }
