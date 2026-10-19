#include <math.h>
#include <string.h>

#include "srm_ctrl.h"
#include "srm_sim.h"

#define QUEUE_SIZE 65536
#define SLOW_PERIOD_S 1.0e-3
#define TWO_PI 6.283185307179586476925286766559

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
    double theta, omega;
    double psi[SRM_SIM_MAX_PHASES], cur[SRM_SIM_MAX_PHASES], trq[SRM_SIM_MAX_PHASES], wf[SRM_SIM_MAX_PHASES];
    srm_adc_t adc;
    int adc_counts[SRM_SIM_MAX_PHASES];
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
    return channel < S.cfg->n_phases ? (uint16_t)S.adc_counts[channel] : 0;
}

static uint32_t hal_encoder_count(void)
{
    return srm_encoder_count(S.cfg, S.theta);
}

static void hal_resolver_sincos(int16_t *s, int16_t *c)
{
    *s = 0;
    *c = 0;
    if (S.cfg->resolver) srm_resolver(S.cfg, S.theta, s, c);
}

static uint32_t hal_micros(void)
{
    return (uint32_t)(int64_t)llround((double)S.n * S.cfg->dt * 1.0e6);
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
    for (int k = 0; k < S.cfg->n_phases; k++) S.adc_counts[k] = srm_adc_convert(&S.adc, S.cfg, k);
}

static double eps(void)
{
    return TWO_PI / ((double)S.cfg->n_phases * (double)S.cfg->n_rotor_poles);
}

/* i, T and W of every phase at rotor angle theta and fluxes psi; returns the total torque. */
static double eval_all(double theta, const double *psi, double *i, double *t, double *w)
{
    double sum = 0.0;
    for (int k = 0; k < S.cfg->n_phases; k++) {
        srm_motor_eval(S.tab, theta - (double)k * eps(), psi[k], &i[k], &t[k], &w[k]);
        sum += t[k];
    }
    return sum;
}

static double load_torque(double t)
{
    return S.cfg->load + (t >= S.cfg->load_step_time ? S.cfg->load_step : 0.0);
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
        cfg->adc_bits < 1 || cfg->adc_bits > 16 ||
        cfg->resolver_bits < 2 || cfg->resolver_bits > 16 || cfg->resolver_pole_pairs < 1)
        return -1;
    memset(&S, 0, sizeof S);
    S.cfg = cfg;
    S.tab = tab;
    S.delay_steps = step_of(cfg->compute_delay, cfg->dt);
    S.theta = cfg->theta0;
    S.omega = cfg->speed;
    srm_conv_init(&S.conv, cfg);
    memset(sum, 0, sizeof *sum);
    sum->torque_min = INFINITY;
    sum->torque_max = -INFINITY;

    const double dt = cfg->dt, R = cfg->resistance;
    const int dynamic = cfg->mode == 1;
    double ttot = eval_all(S.theta, S.psi, S.cur, S.trq, S.wf);
    for (int k = 0; k < q; k++) sum->w_field_start += S.wf[k];

    srm_adc_init(&S.adc, cfg, S.cur);

    srm_hal_t hal = {0};
    hal.n_phases = (uint8_t)q;
    hal.pwm_hz = (float)cfg->pwm_hz;
    hal.isr_hz = (float)cfg->isr_hz;
    hal.adc_bits = (uint8_t)cfg->adc_bits;
    hal.adc_amps_per_count = (float)cfg->adc_amps_per_count;
    hal.adc_offset_counts = cfg->adc_offset_counts;
    hal.encoder_cpr = cfg->encoder_cpr;
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

    int64_t isr_k = 0, slow_k = 1;
    int64_t next_isr = step_of(0.5 / cfg->isr_hz, dt), next_slow = step_of(SLOW_PERIOD_S, dt);
    const int64_t window_start = cfg->n_steps / 2;
    double adc_hold[SRM_SIM_MAX_PHASES] = {0};
    int64_t n_out = 0;

    for (int64_t n = 0; n < cfg->n_steps; n++) {
        const double t = (double)n * dt;
        S.n = n;
        while (n >= next_isr) {
            latch_adc();
            S.in_isr = 1;
            ctrl_isr();
            S.in_isr = 0;
            next_isr = step_of(((double)(++isr_k) + 0.5) / cfg->isr_hz, dt);
        }
        while (n >= next_slow) {
            ctrl_slow();
            next_slow = step_of((double)(++slow_k) * SLOW_PERIOD_S, dt);
        }
        while (S.q_head < S.q_tail && S.queue[S.q_head % QUEUE_SIZE].step <= n) apply_event(&S.queue[S.q_head++ % QUEUE_SIZE]);
        if (S.overflow) return -2;
        srm_conv_step(&S.conv, t);

        double v[SRM_SIM_MAX_PHASES], pin = 0.0, cu = 0.0;
        int beyond = 0;
        for (int k = 0; k < q; k++) {
            v[k] = srm_conv_voltage(&S.conv, k, S.cur[k]);
            pin += v[k] * S.cur[k];
            cu += R * S.cur[k] * S.cur[k];
            if (S.cur[k] > tab->i_max || S.psi[k] > tab->psi_max) beyond = 1;
            adc_hold[k] = adc_amps(S.adc_counts[k]);
        }
        sum->beyond_map_steps += beyond;
        const double pmech = ttot * S.omega;

        if (n % cfg->trace_stride == 0) {
            int64_t o = n / cfg->trace_stride;
            trace->t[o] = t;
            trace->theta[o] = S.theta;
            trace->omega[o] = S.omega;
            trace->torque[o] = ttot;
            trace->encoder[o] = (double)hal_encoder_count();
            int16_t rs, rc;
            hal_resolver_sincos(&rs, &rc);
            trace->resolver_sin[o] = rs;
            trace->resolver_cos[o] = rc;
            for (int k = 0; k < q; k++) {
                int64_t at = (int64_t)k * trace->n_samples + o;
                trace->i[at] = (float)S.cur[k];
                trace->psi[at] = (float)S.psi[k];
                trace->v[at] = (float)v[k];
                trace->adc_i[at] = (float)adc_hold[k];
                trace->gate_u[at] = (uint8_t)S.conv.ph[k].u_eff;
                trace->gate_l[at] = (uint8_t)S.conv.ph[k].l_eff;
            }
            n_out = o + 1;
        }
        if (n >= window_start) {
            sum->window_steps++;
            sum->torque_sum += ttot;
            if (ttot < sum->torque_min) sum->torque_min = ttot;
            if (ttot > sum->torque_max) sum->torque_max = ttot;
            sum->copper_sum += cu;
            sum->power_in_sum += pin;
            sum->power_mech_sum += pmech;
            for (int k = 0; k < q; k++) sum->i2_sum[k] += S.cur[k] * S.cur[k];
        }

        /* Heun step with the converter voltage held over the step */
        const double load0 = load_torque(t), load1 = load_torque(t + dt);
        double k1[SRM_SIM_MAX_PHASES], psi_p[SRM_SIM_MAX_PHASES], i_p[SRM_SIM_MAX_PHASES], t_p[SRM_SIM_MAX_PHASES],
            w_p[SRM_SIM_MAX_PHASES];
        const double a1 = dynamic ? (ttot - cfg->friction * S.omega - load0) / cfg->inertia : 0.0;
        for (int k = 0; k < q; k++) {
            k1[k] = v[k] - R * S.cur[k];
            psi_p[k] = S.psi[k] + dt * k1[k];
        }
        const double omega_p = S.omega + dt * a1;
        const double tt_p = eval_all(S.theta + dt * S.omega, psi_p, i_p, t_p, w_p);
        const double a2 = dynamic ? (tt_p - cfg->friction * omega_p - load1) / cfg->inertia : 0.0;
        for (int k = 0; k < q; k++) {
            double psi = S.psi[k] + 0.5 * dt * (k1[k] + (v[k] - R * i_p[k]));
            S.psi[k] = psi > 0.0 ? psi : 0.0;
        }
        const double theta_new = dynamic ? S.theta + 0.5 * dt * (S.omega + omega_p)
                                         : cfg->theta0 + cfg->speed * (double)(n + 1) * dt;
        const double omega_new = S.omega + 0.5 * dt * (a1 + a2);
        double i_old[SRM_SIM_MAX_PHASES];
        memcpy(i_old, S.cur, sizeof i_old);
        const double ttot_new = eval_all(theta_new, S.psi, S.cur, S.trq, S.wf);
        for (int k = 0; k < q; k++) {
            sum->energy_in += dt * v[k] * 0.5 * (i_old[k] + S.cur[k]);
            sum->energy_copper += dt * R * 0.5 * (i_old[k] * i_old[k] + S.cur[k] * S.cur[k]);
        }
        sum->energy_mech += dt * 0.5 * (pmech + ttot_new * omega_new);
        S.theta = theta_new;
        S.omega = omega_new;
        ttot = ttot_new;
        srm_adc_filter(&S.adc, cfg, S.cur);
    }
    for (int k = 0; k < q; k++) sum->w_field_end += S.wf[k];
    trace->n_samples = n_out;
    return 0;
}
