#include <math.h>
#include <string.h>

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

int64_t srm_sensor_delay_steps(const srm_sim_config_t *c)
{
    return (int64_t)floor(c->sensor_delay / c->dt + 0.5);
}

int64_t srm_sensor_jitter_steps(const srm_sim_config_t *c)
{
    if (!(c->sensor_delay_jitter > 0.0)) return 0;
    return (int64_t)floor((c->sensor_delay + c->sensor_delay_jitter) / c->dt + 0.5) - srm_sensor_delay_steps(c);
}

void srm_adc_init(srm_adc_t *a, const srm_sim_config_t *c, const double *current)
{
    a->alpha = c->adc_rc_tau > 0.0 ? 1.0 - exp(-c->dt / c->adc_rc_tau) : 1.0;
    a->v_alpha = c->volt_rc_tau > 0.0 ? 1.0 - exp(-c->dt / c->volt_rc_tau) : 1.0;
    a->delay_steps = srm_sensor_delay_steps(c);
    a->pos = 0;
    for (int k = 0; k < c->n_phases; k++) {
        a->filtered[k] = current[k];
        a->v_filtered[k] = 0.0;
    }
    for (int64_t s = 0; s < a->delay_steps; s++)
        for (int k = 0; k < c->n_phases; k++) {
            a->ring[s][k] = (float)current[k];
            a->ring[s][SRM_SIM_MAX_PHASES + k] = 0.0f;
        }
    a->hist_len = c->sensor_delay_jitter > 0.0 ? srm_sensor_jitter_steps(c) + 1 : 0;
    a->hpos = 0;
    for (int64_t s = 0; s < a->hist_len; s++)
        for (int k = 0; k < c->n_phases; k++) {
            a->hist[s][k] = current[k];
            a->hist[s][SRM_SIM_MAX_PHASES + k] = 0.0;
        }
    srm_rng_seed(&a->rng, c->seed);
}

/* The value pushed delay_steps calls ago for ring channel ch; the input itself without a delay. */
static double delayed(srm_adc_t *a, int ch, double x)
{
    if (a->delay_steps == 0) return x;
    double out = (double)a->ring[a->pos][ch];
    a->ring[a->pos][ch] = (float)x;
    return out;
}

/* Advance the delay and the first-order filters on the sensed currents and voltages by one step. */
void srm_adc_filter(srm_adc_t *a, const srm_sim_config_t *c, const double *current, const double *volts)
{
    for (int k = 0; k < c->n_phases; k++) {
        a->filtered[k] += a->alpha * (delayed(a, k, current[k]) - a->filtered[k]);
        a->v_filtered[k] += a->v_alpha * (delayed(a, SRM_SIM_MAX_PHASES + k, volts[k]) - a->v_filtered[k]);
    }
    if (a->delay_steps > 0 && ++a->pos == a->delay_steps) a->pos = 0;
    if (a->hist_len > 0) {
        for (int k = 0; k < c->n_phases; k++) {
            a->hist[a->hpos][k] = a->filtered[k];
            a->hist[a->hpos][SRM_SIM_MAX_PHASES + k] = a->v_filtered[k];
        }
        if (++a->hpos == a->hist_len) a->hpos = 0;
    }
}

/* The extra age e = round((sensor_delay + u * jitter) / dt) - delay steps, u uniform in [0, 1): the values of e
   steps before the newest entry. */
void srm_adc_sample(srm_adc_t *a, const srm_sim_config_t *c)
{
    if (a->hist_len == 0) return;
    double u = (double)(next_u64(&a->rng) >> 11) * U53;
    int64_t e = (int64_t)floor((c->sensor_delay + u * c->sensor_delay_jitter) / c->dt + 0.5) - a->delay_steps;
    if (e < 0) e = 0;
    if (e > a->hist_len - 1) e = a->hist_len - 1;
    int64_t at = (a->hpos - 1 - e + 2 * a->hist_len) % a->hist_len;
    memcpy(a->held, a->hist[at], sizeof a->held);
}

int srm_adc_convert(srm_adc_t *a, const srm_sim_config_t *c, int phase)
{
    double x = (double)c->adc_offset_counts + c->adc_offset_error +
               (a->hist_len ? a->held[phase] : a->filtered[phase]) * (1.0 + c->adc_gain_error) / c->adc_amps_per_count;
    if (c->adc_noise > 0.0) x += c->adc_noise * srm_rng_gauss(&a->rng);
    double top = (double)((1 << c->adc_bits) - 1);
    x = floor(x + 0.5);
    return (int)(x < 0.0 ? 0.0 : (x > top ? top : x));
}

int srm_adc_convert_volt(const srm_adc_t *a, const srm_sim_config_t *c, int phase)
{
    double top = (double)((1 << c->adc_bits) - 1);
    double v = a->hist_len ? a->held[SRM_SIM_MAX_PHASES + phase] : a->v_filtered[phase];
    double x = floor((double)(1 << (c->adc_bits - 1)) + v / (2.0 * c->volt_full_scale) * top + 0.5);
    return (int)(x < 0.0 ? 0.0 : (x > top ? top : x));
}
