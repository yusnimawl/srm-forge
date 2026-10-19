/* Test controller: reads every sensor each ISR and leaves all gates off. */
#include "srm_ctrl.h"
#include "srm_motor_tables.h"

static const srm_hal_t *hal;
volatile uint32_t probe_sink;

void ctrl_init(const srm_hal_t *h) { hal = h; }
int ctrl_param(const char *name, float value) { (void)name; (void)value; return -1; }
void ctrl_command(srm_cmd_mode_t mode, float value) { (void)mode; (void)value; }

void ctrl_isr(void)
{
    int16_t s, c;
    uint32_t sum = hal->encoder_count();
    for (uint8_t k = 0; k < hal->n_phases; k++) sum += hal->adc_read(k);
    hal->resolver_sincos(&s, &c);
    probe_sink = sum + (uint32_t)(int32_t)s + (uint32_t)(int32_t)c;
}

void ctrl_slow(void) {}
