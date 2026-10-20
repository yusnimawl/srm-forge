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

typedef struct {
    double alpha;
    double filtered[SRM_SIM_MAX_PHASES];
    srm_rng_t rng;
} srm_adc_t;

void srm_rng_seed(srm_rng_t *r, uint32_t seed);
double srm_rng_gauss(srm_rng_t *r);
uint32_t srm_encoder_count(const srm_sim_config_t *c, double theta);
void srm_resolver(const srm_sim_config_t *c, double theta, int16_t *s, int16_t *co);
void srm_adc_init(srm_adc_t *a, const srm_sim_config_t *c, const double *current);
void srm_adc_filter(srm_adc_t *a, const srm_sim_config_t *c, const double *current);
int srm_adc_convert(srm_adc_t *a, const srm_sim_config_t *c, int phase);

#endif
