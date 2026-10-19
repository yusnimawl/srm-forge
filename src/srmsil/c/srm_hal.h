#ifndef SRM_HAL_H
#define SRM_HAL_H

#include <stdbool.h>
#include <stdint.h>

typedef enum { SRM_CHOP_HARD, SRM_CHOP_SOFT } srm_chop_t;

typedef struct {
    uint8_t  n_phases;
    float    pwm_hz;              /* PWM carrier; ctrl_isr runs once per period */
    float    isr_hz;              /* ctrl_isr rate (= pwm_hz unless the scenario sets a faster sampled loop) */
    uint8_t  adc_bits;
    float    adc_amps_per_count;  /* nominal scale; real gain/offset errors are not visible to the controller */
    int32_t  adc_offset_counts;   /* nominal zero-current reading */
    uint32_t encoder_cpr;         /* counts per mechanical revolution, 0 when no encoder */
    void     (*set_switches)(uint8_t phase, bool upper, bool lower);   /* direct gate control */
    void     (*set_pwm)(uint8_t phase, float duty, srm_chop_t mode);   /* duty 0..1; timer adds dead time */
    uint16_t (*adc_read)(uint8_t channel);                             /* channel = phase for currents */
    uint32_t (*encoder_count)(void);
    void     (*resolver_sincos)(int16_t *s, int16_t *c);               /* raw signed ADC counts */
    uint32_t (*micros)(void);
    float    (*vbus_volts)(void);                                      /* DC bus voltage as a driver measures it */
} srm_hal_t;

#endif
