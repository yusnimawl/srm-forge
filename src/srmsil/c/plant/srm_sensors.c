#include <math.h>

#include "srm_sensors.h"

#define TWO_PI 6.283185307179586476925286766559
#define U53 (1.0 / 9007199254740992.0)

/* The integer stream is identical on every platform; the Gaussian values agree to libm precision.
   xorshift64* seeded through splitmix64, then Box-Muller: the same draws on every platform. */
static uint64_t next_u64(srm_rng_t *r)
{
    uint64_t x = r->s;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    r->s = x;
    return x * 0x2545F4914F6CDD1DULL;
}

void srm_rng_seed(srm_rng_t *r, uint32_t seed)
{
    uint64_t z = (uint64_t)seed + 0x9E3779B97F4A7C15ULL;
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    z ^= z >> 31;
    r->s = z ? z : 0x9E3779B97F4A7C15ULL;
    r->have = 0;
    r->spare = 0.0;
}

double srm_rng_gauss(srm_rng_t *r)
{
    if (r->have) {
        r->have = 0;
        return r->spare;
    }
    double u1 = (double)((next_u64(r) >> 11) + 1) * U53;
    double u2 = (double)(next_u64(r) >> 11) * U53;
    double m = sqrt(-2.0 * log(u1));
    r->spare = m * sin(TWO_PI * u2);
    r->have = 1;
    return m * cos(TWO_PI * u2);
}

static double measured_angle(const srm_sim_config_t *c, double theta)
{
    return theta + c->encoder_offset + c->encoder_ecc_amp * sin((double)c->encoder_ecc_harmonic * theta);
}

/* Single-turn count in [0, cpr), like a timer in encoder mode with ARR = cpr - 1. */
uint32_t srm_encoder_count(const srm_sim_config_t *c, double theta)
{
    if (c->encoder_cpr == 0) return 0;
    double turns = measured_angle(c, theta) / TWO_PI;
    turns -= floor(turns);
    uint32_t n = (uint32_t)(turns * (double)c->encoder_cpr);
    return n >= c->encoder_cpr ? c->encoder_cpr - 1 : n;
}

/* The resolver channels clamp to int16. */
static int16_t to_i16(double x)
{
    x = floor(x + 0.5);
    return (int16_t)(x > 32767.0 ? 32767.0 : (x < -32768.0 ? -32768.0 : x));
}

void srm_resolver(const srm_sim_config_t *c, double theta, int16_t *s, int16_t *co)
{
    double amp = (double)((1 << (c->resolver_bits - 1)) - 1);
    double x = (double)c->resolver_pole_pairs * measured_angle(c, theta);
    *s = to_i16(amp * sin(x));
    *co = to_i16(amp * (1.0 + c->resolver_gain_mismatch) * cos(x + c->resolver_phase_error));
}

void srm_adc_init(srm_adc_t *a, const srm_sim_config_t *c, const double *current)
{
    a->alpha = c->adc_rc_tau > 0.0 ? 1.0 - exp(-c->dt / c->adc_rc_tau) : 1.0;
    for (int k = 0; k < c->n_phases; k++) a->filtered[k] = current[k];
    srm_rng_seed(&a->rng, c->seed);
}

/* Advance the first-order filter on the sensed current by one step. */
void srm_adc_filter(srm_adc_t *a, const srm_sim_config_t *c, const double *current)
{
    for (int k = 0; k < c->n_phases; k++) a->filtered[k] += a->alpha * (current[k] - a->filtered[k]);
}

int srm_adc_convert(srm_adc_t *a, const srm_sim_config_t *c, int phase)
{
    double x = (double)c->adc_offset_counts + c->adc_offset_error +
               a->filtered[phase] * (1.0 + c->adc_gain_error) / c->adc_amps_per_count;
    if (c->adc_noise > 0.0) x += c->adc_noise * srm_rng_gauss(&a->rng);
    double top = (double)((1 << c->adc_bits) - 1);
    x = floor(x + 0.5);
    return (int)(x < 0.0 ? 0.0 : (x > top ? top : x));
}
