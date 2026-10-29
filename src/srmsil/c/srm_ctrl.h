#ifndef SRM_CTRL_H
#define SRM_CTRL_H

#include "srm_hal.h"

typedef enum { SRM_CMD_TORQUE, SRM_CMD_SPEED } srm_cmd_mode_t;

/* Functions a controller provides. */
void ctrl_init(const srm_hal_t *hal);
/* Set a tunable by name; may be called before ctrl_init and at any time while running.
 * 0 = accepted, -1 = unknown name, -2 = known but not changeable while running. */
int  ctrl_param(const char *name, float value);
void ctrl_command(srm_cmd_mode_t mode, float value); /* SRM_CMD_TORQUE (N*m) or SRM_CMD_SPEED (rad/s) */
void ctrl_isr(void);                                 /* after each ADC conversion, at isr_hz */
void ctrl_slow(void);                                /* 1 kHz: speed loop, supervision */

#endif
