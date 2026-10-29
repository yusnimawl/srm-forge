#include <math.h>
#include <string.h>

#include "srm_ctrl.h"
#include "srm_sim.h"

#define QUEUE_SIZE 65536
#define SLOW_PERIOD_S 1.0e-3

typedef struct {
    int64_t step;
    int phase, pwm, upper, lower, chop;
    double duty;
} gate_event_t;

typedef struct {
    const srm_sim_config_t *cfg;
    const srm_sim_tables_t *tab;
    srm_conv_t conv;
    int64_t n, delay_steps;
    int in_isr, overflow;
    srm_plant_t pl;
    srm_adc_t adc;
    int adc_counts[SRM_SIM_MAX_PHASES], adc_vcounts[SRM_SIM_MAX_PHASES];
    gate_event_t queue[QUEUE_SIZE];
    int64_t q_head, q_tail;
} sim_t;

static sim_t S;

/* HAL, as the controller sees it */

static void apply_event(const gate_event_t *e)
{
    if (e->pwm) srm_conv_set_pwm(&S.conv, e->phase, e->duty, e->chop);
    else srm_conv_set_direct(&S.conv, e->phase, e->upper, e->lower);
}

static void post(const gate_event_t *e)
{
    if (e->phase < 0 || e->phase >= S.cfg->n_phases) return;
    if (!S.in_isr || S.delay_steps == 0) {
        apply_event(e);
        return;
    }
    if (S.q_tail - S.q_head >= QUEUE_SIZE) {
        S.overflow = 1;
        return;
    }
    gate_event_t q = *e;
    q.step = S.n + S.delay_steps;
    S.queue[S.q_tail++ % QUEUE_SIZE] = q;
}

static void hal_set_switches(uint8_t phase, bool upper, bool lower)
{
    gate_event_t e = {0};
    e.phase = phase;
    e.upper = upper;
    e.lower = lower;
    post(&e);
}

static void hal_set_pwm(uint8_t phase, float duty, srm_chop_t mode)
{
    gate_event_t e = {0};
    e.phase = phase;
    e.pwm = 1;
    e.duty = duty;
    e.chop = mode == SRM_CHOP_SOFT;
    post(&e);
}

static uint16_t hal_adc_read(uint8_t channel)
{
    const int q = S.cfg->n_phases;
    if (channel < q) return (uint16_t)S.adc_counts[channel];
    if (channel < 2 * q && S.cfg->volt_full_scale > 0.0) return (uint16_t)S.adc_vcounts[channel - q];
    return 0;
}

static uint32_t hal_encoder_count(void)
{
    return srm_encoder_count(S.cfg, S.pl.theta);
}

static void hal_resolver_sincos(int16_t *s, int16_t *c)
{
    *s = 0;
    *c = 0;
    if (S.cfg->resolver) srm_resolver(S.cfg, S.pl.theta, s, c);
}

static uint32_t hal_micros(void)
{
    return (uint32_t)(int64_t)llround((double)S.n * S.cfg->dt * 1.0e6 * S.cfg->controller_clock);
}

static float hal_vbus_volts(void)
{
    return (float)S.cfg->bus_voltage;
}

/* Simulation */

static double adc_amps(int counts)
{
    return (double)(counts - S.cfg->adc_offset_counts) * S.cfg->adc_amps_per_count;
}

static void latch_adc(void)
{
    srm_adc_sample(&S.adc, S.cfg);
    for (int k = 0; k < S.cfg->n_phases; k++) {
        S.adc_counts[k] = srm_adc_convert(&S.adc, S.cfg, k);
        if (S.cfg->volt_full_scale > 0.0) S.adc_vcounts[k] = srm_adc_convert_volt(&S.adc, S.cfg, k);
    }
}

static double adc_volts(int counts)
{
    return (double)(counts - (1 << (S.cfg->adc_bits - 1))) * 2.0 * S.cfg->volt_full_scale /
           (double)((1 << S.cfg->adc_bits) - 1);
}

int srm_sim_abi(void) { return SRM_SIM_ABI; }
size_t srm_sim_sizeof_config(void) { return sizeof(srm_sim_config_t); }
size_t srm_sim_sizeof_tables(void) { return sizeof(srm_sim_tables_t); }
size_t srm_sim_sizeof_trace(void) { return sizeof(srm_sim_trace_t); }
size_t srm_sim_sizeof_summary(void) { return sizeof(srm_sim_summary_t); }

int srm_sim_param(const char *name, float value)
{
    return ctrl_param(name, value);
}

static int64_t step_of(double seconds, double dt)
{
    return (int64_t)llround(seconds / dt);
}

int srm_sim_run(const srm_sim_config_t *cfg, const srm_sim_tables_t *tab, srm_sim_trace_t *trace,
                srm_sim_summary_t *sum)
{
    const int q = cfg->n_phases;
    if (q < 1 || q > SRM_SIM_MAX_PHASES || cfg->n_steps < 1 || !(cfg->dt > 0.0) || cfg->trace_stride < 1 ||
        cfg->adc_bits < 1 || cfg->adc_bits > 16 || !(cfg->sensor_delay >= 0.0) || !(cfg->volt_full_scale >= 0.0) ||
        !(cfg->volt_rc_tau >= 0.0) || srm_sensor_delay_steps(cfg) > SRM_DELAY_MAX || cfg->n_param_steps < 0 ||
        (cfg->n_param_steps > 0 && !cfg->param_steps) ||
        cfg->resolver_bits < 2 || cfg->resolver_bits > 16 || cfg->resolver_pole_pairs < 1 ||
        !(cfg->controller_clock > 0.0) || !(cfg->sensor_delay_jitter >= 0.0) ||
        srm_sensor_jitter_steps(cfg) + 1 > SRM_DELAY_MAX)
        return -1;
    memset(&S, 0, sizeof S);
    S.cfg = cfg;
    S.tab = tab;
    S.delay_steps = step_of(cfg->compute_delay, cfg->dt);
    srm_conv_init(&S.conv, cfg);
    memset(sum, 0, sizeof *sum);
    sum->torque_min = INFINITY;
    sum->torque_max = -INFINITY;

    const double dt = cfg->dt, R = cfg->resistance;
    srm_plant_init(&S.pl, cfg, tab);
    for (int k = 0; k < q; k++) sum->w_field_start += S.pl.wf[k];

    srm_adc_init(&S.adc, cfg, S.pl.cur);

    srm_hal_t hal = {0};
    hal.n_phases = (uint8_t)q;
    hal.pwm_hz = (float)cfg->pwm_hz;
    hal.isr_hz = (float)cfg->isr_hz;
    hal.adc_bits = (uint8_t)cfg->adc_bits;
    hal.adc_amps_per_count = (float)cfg->adc_amps_per_count;
    hal.adc_offset_counts = cfg->adc_offset_counts;
    hal.encoder_cpr = cfg->encoder_cpr;
    if (cfg->volt_full_scale > 0.0) {
        hal.adc_volts_per_count = (float)(2.0 * cfg->volt_full_scale / (double)((1 << cfg->adc_bits) - 1));
        hal.adc_volt_offset_counts = 1 << (cfg->adc_bits - 1);
    }
    hal.set_switches = hal_set_switches;
    hal.set_pwm = hal_set_pwm;
    hal.adc_read = hal_adc_read;
    hal.encoder_count = hal_encoder_count;
    hal.resolver_sincos = hal_resolver_sincos;
    hal.micros = hal_micros;
    hal.vbus_volts = hal_vbus_volts;

    latch_adc();
    ctrl_init(&hal);
    ctrl_command(cfg->command_mode == 1 ? SRM_CMD_SPEED : SRM_CMD_TORQUE, (float)cfg->command_value);

    /* ISR and ctrl_slow instants in true time, on the controller's clock */
    const double isr_hz = cfg->isr_hz * cfg->controller_clock, slow_period = SLOW_PERIOD_S / cfg->controller_clock;
    int64_t isr_k = 0, slow_k = 1;
    int64_t next_isr = step_of(0.5 / isr_hz, dt), next_slow = step_of(slow_period, dt);
    const int64_t window_start = cfg->n_steps / 2;
    double adc_hold[SRM_SIM_MAX_PHASES] = {0}, adc_vhold[SRM_SIM_MAX_PHASES] = {0};
    int32_t next_step = 0;
    int64_t n_out = 0;

    for (int64_t n = 0; n < cfg->n_steps; n++) {
        const double t = (double)n * dt;
        S.n = n;
        while (n >= next_isr) {
            while (next_step < cfg->n_param_steps && cfg->param_steps[next_step].t <= t + 1.0e-9 * dt) {
                char name[sizeof cfg->param_steps[0].name];
                memcpy(name, cfg->param_steps[next_step].name, sizeof name);
                name[sizeof name - 1] = '\0';
                int rc = ctrl_param(name, cfg->param_steps[next_step].value);
                next_step++;
                if (rc != 0) {
                    sum->refused = next_step;
                    sum->refused_code = rc;
                    return -3;
                }
            }
            latch_adc();
            S.in_isr = 1;
            ctrl_isr();
            S.in_isr = 0;
            next_isr = step_of(((double)(++isr_k) + 0.5) / isr_hz, dt);
        }
        while (n >= next_slow) {
            ctrl_slow();
            next_slow = step_of((double)(++slow_k) * slow_period, dt);
        }
        while (S.q_head < S.q_tail && S.queue[S.q_head % QUEUE_SIZE].step <= n) apply_event(&S.queue[S.q_head++ % QUEUE_SIZE]);
        if (S.overflow) return -2;
        srm_conv_step(&S.conv, t);

        double v[SRM_SIM_MAX_PHASES], pin = 0.0, cu = 0.0;
        int beyond = 0;
        for (int k = 0; k < q; k++) {
            v[k] = srm_conv_voltage(&S.conv, k, S.pl.cur[k]);
            pin += v[k] * S.pl.cur[k];
            cu += R * S.pl.cur[k] * S.pl.cur[k];
            if (S.pl.cur[k] > tab->i_max || S.pl.psi[k] > tab->psi_max) beyond = 1;
            adc_hold[k] = adc_amps(S.adc_counts[k]);
            if (cfg->volt_full_scale > 0.0) adc_vhold[k] = adc_volts(S.adc_vcounts[k]);
        }
        sum->beyond_map_steps += beyond;
        const double pmech = S.pl.ttot * S.pl.omega;

        if (n % cfg->trace_stride == 0) {
            int64_t o = n / cfg->trace_stride;
            trace->t[o] = t;
            trace->theta[o] = S.pl.theta;
            trace->omega[o] = S.pl.omega;
            trace->torque[o] = S.pl.ttot;
            trace->encoder[o] = (double)hal_encoder_count();
            int16_t rs, rc;
            hal_resolver_sincos(&rs, &rc);
            trace->resolver_sin[o] = rs;
            trace->resolver_cos[o] = rc;
            for (int k = 0; k < q; k++) {
                int64_t at = (int64_t)k * trace->n_samples + o;
                trace->i[at] = (float)S.pl.cur[k];
                trace->psi[at] = (float)S.pl.psi[k];
                trace->v[at] = (float)v[k];
                trace->adc_i[at] = (float)adc_hold[k];
                trace->adc_v[at] = (float)adc_vhold[k];
                trace->gate_u[at] = (uint8_t)S.conv.ph[k].u_eff;
                trace->gate_l[at] = (uint8_t)S.conv.ph[k].l_eff;
            }
            n_out = o + 1;
        }
        if (n >= window_start) {
            sum->window_steps++;
            sum->torque_sum += S.pl.ttot;
            if (S.pl.ttot < sum->torque_min) sum->torque_min = S.pl.ttot;
            if (S.pl.ttot > sum->torque_max) sum->torque_max = S.pl.ttot;
            sum->copper_sum += cu;
            sum->power_in_sum += pin;
            sum->power_mech_sum += pmech;
            for (int k = 0; k < q; k++) sum->i2_sum[k] += S.pl.cur[k] * S.pl.cur[k];
        }

        double i_old[SRM_SIM_MAX_PHASES];
        memcpy(i_old, S.pl.cur, sizeof i_old);
        srm_plant_step(&S.pl, cfg, tab, v, t, n);
        for (int k = 0; k < q; k++) {
            sum->energy_in += dt * v[k] * 0.5 * (i_old[k] + S.pl.cur[k]);
            sum->energy_copper += dt * R * 0.5 * (i_old[k] * i_old[k] + S.pl.cur[k] * S.pl.cur[k]);
        }
        sum->energy_mech += dt * 0.5 * (pmech + S.pl.ttot * S.pl.omega);
        srm_adc_filter(&S.adc, cfg, S.pl.cur, v);
    }
    for (int k = 0; k < q; k++) sum->w_field_end += S.pl.wf[k];
    trace->n_samples = n_out;
    return 0;
}
