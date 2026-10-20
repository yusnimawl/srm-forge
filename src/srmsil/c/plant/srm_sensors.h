#ifndef SRM_SENSORS_H
#define SRM_SENSORS_H

#include <stdint.h>

#include "srm_plant.h"

/* Sensors: encoder and resolver readings from the rotor angle, and the ADC chain (RC filter, offset, gain, noise,
   quantisation) on the phase currents. */
typedef struct {
    uint64_t s;
    int have;
    double spare;
} srm_rng_t;

/* Longest sensor transport delay in simulation steps. */
#define SRM_DELAY_MAX 2048

typedef struct {
    double alpha, v_alpha;
    double filtered[SRM_SIM_MAX_PHASES], v_filtered[SRM_SIM_MAX_PHASES];
    int64_t delay_steps, pos;
    float ring[SRM_DELAY_MAX][2 * SRM_SIM_MAX_PHASES];   /* delayed currents, then voltages */
    srm_rng_t rng;
} srm_adc_t;

void srm_rng_seed(srm_rng_t *r, uint32_t seed);
double srm_rng_gauss(srm_rng_t *r);
uint32_t srm_encoder_count(const srm_sim_config_t *c, double theta);
void srm_resolver(const srm_sim_config_t *c, double theta, int16_t *s, int16_t *co);
void srm_adc_init(srm_adc_t *a, const srm_sim_config_t *c, const double *current);
/* Steps of sensor delay, round(sensor_delay / dt). */
int64_t srm_sensor_delay_steps(const srm_sim_config_t *c);
/* Push the phase currents and winding voltages of this step through the delay and the filters. */
void srm_adc_filter(srm_adc_t *a, const srm_sim_config_t *c, const double *current, const double *volts);
int srm_adc_convert(srm_adc_t *a, const srm_sim_config_t *c, int phase);
/* Bipolar voltage code of a phase: 2^(bits-1) at 0 V, 2^bits - 1 at +volt_full_scale. */
int srm_adc_convert_volt(const srm_adc_t *a, const srm_sim_config_t *c, int phase);

#endif
