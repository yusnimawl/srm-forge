// 200 kHz step interrupt: the gate edges of each 5 us window are averaged into winding voltages and the shared plant
// takes one step; the order mirrors src/srmsil/c/emu/srm_emu.c, the PC model of this loop.
#include <Arduino.h>
#include <IntervalTimer.h>
#include <math.h>
#include <string.h>

#include "emu.h"

srm_table_t g_current[EMU_MAX_THETA * EMU_MAX_PSI], g_torque[EMU_MAX_THETA * EMU_MAX_PSI];   // DTCM
emu_edge_ring_t g_edges;
volatile bool g_selftest;

#define EMU_TWO_PI 6.283185307179586
#define MARGIN 300               // cycles: a window closes this long before the step interrupt that takes it
#define MAX_EDGES 64             // per window; later edges are taken by the next window

static hil_emu_config_t cfg;
static bool cfg_ok;
static srm_sim_config_t sim;
static srm_sim_tables_t tab;
static uint32_t got[2];          // entries [0, got) of each table received in order since the config
static IntervalTimer timer;
static volatile bool running;
static volatile bool overloaded;

// Step-interrupt state (written only there while running).
static srm_plant_t pl;
static srm_gate_avg_t ga;
static uint32_t P;               // cycles per step
static uint64_t clk, base, n_win;
static int64_t n_step;
static bool armed, fault;
static emu_pattern_t pat;
static bool pat_on;
static volatile bool st_pending;
static volatile float st_duty;
static volatile uint16_t st_word = 0x0101;     // both switches of the pattern's phases
static float i_scale, psi_scale, v_scale, t_scale, w_scale;
static float inv_i, inv_psi, inv_v, inv_t, inv_w;     // inverse scales, for the step interrupt
static uint32_t edge_overflows_seen;
static uint16_t last_word;
static uint64_t last_rise;

// Health and statistics.
static volatile uint32_t overruns;
static uint32_t step_max, prof_ga, prof_pl;    // cycles, since start
static uint64_t prof_ga_sum, prof_pl_sum, prof_exec_sum, prof_n;
struct Window {
    uint32_t calls, steps, lat_n;
    uint64_t exec_sum, lat_sum;
    float t_sum, t_min, t_max, i2[EMU_MAX_PHASES];      // per step, single precision
    double per_n, per_sum, per_sq;                        // per gate edge
};
static Window w;
static hil_live_emu_t pub[2];
static volatile uint8_t pub_idx;
static volatile bool pub_new;

// With the step timer stopped: a pending pattern change is dropped and the self-test flag follows the duty, so a
// pattern switched off just before a stop cannot leave the gate inputs and RUN overridden.
static void selftest_settle()
{
    st_pending = false;
    g_selftest = st_duty > 0.0f;
}

static void window_reset()
{
    memset(&w, 0, sizeof w);
    w.t_min = INFINITY;
    w.t_max = -INFINITY;
}

static void publish()
{
    hil_live_emu_t &o = pub[pub_idx ^ 1];
    const double f = (double)F_CPU_ACTUAL;
    const double n = w.steps ? (double)w.steps : (double)NAN;
    o.step = (uint32_t)n_step;
    o.mean_torque = (float)((double)w.t_sum / n);
    o.ripple_pct = fabsf(o.mean_torque) > 1e-12f ? (float)(100.0 * (double)(w.t_max - w.t_min) / fabs((double)w.t_sum / n))
                                                : NAN;
    for (int k = 0; k < EMU_MAX_PHASES; k++) o.i_rms[k] = (float)sqrt((double)w.i2[k] / n);
    o.speed_rpm = (float)((double)pl.omega * 60.0 / EMU_TWO_PI);
    o.step_mean_us = (float)((double)w.exec_sum / (double)w.calls / f * 1e6);
    o.step_max_us = (float)((double)step_max / f * 1e6);
    o.overruns = overruns;
    o.dropped = cap_dropped();
    if (w.per_n > 1) {
        double m = w.per_sum / w.per_n, var = w.per_sq / w.per_n - m * m;
        o.edge_jitter_ns = (float)(sqrt(var > 0 ? var : 0) / f * 1e9);
    } else {
        o.edge_jitter_ns = NAN;
    }
    o.latency_us = w.lat_n ? (float)((double)w.lat_sum / w.lat_n / f * 1e6) : NAN;
    o.trigger_hz = outputs_trigger_hz();
    pub_idx ^= 1;
    pub_new = true;
    window_reset();
}

static void step_isr()
{
    clk = emu_clock_extend(clk, ARM_DWT_CYCCNT);
    if (!armed) {
        base = clk - MARGIN;
        armed = true;
        return;
    }
    const uint64_t t0 = base + n_win * P, t1 = t0 + P;
    n_win++;
    if (st_pending) {
        st_pending = false;
        const float d = st_duty;
        pat_on = d > 0.0f;
        const uint64_t period = F_CPU_ACTUAL / EMU_SELFTEST_HZ;
        if (pat_on) emu_pattern_init(&pat, t0 + EMU_SELFTEST_OFFSET, period, (uint64_t)llround(d * period), st_word);
        else {
            emu_edge_push(&g_edges, (uint32_t)t0, 0);     // all off; the gate inputs take over after this edge
            g_selftest = false;
        }
    }
    if (pat_on) emu_pattern_feed(&pat, &g_edges, t1);
    srm_edge_t e[MAX_EDGES];
    const int ne = emu_edge_take(&g_edges, clk, t1, e, MAX_EDGES);
    for (int j = 0; j < ne; j++) {
        if ((e[j].gates & 1) && !(last_word & 1)) {
            if (last_rise) {
                double d = (double)(e[j].t - last_rise);
                w.per_n++;
                w.per_sum += d;
                w.per_sq += d * d;
            }
            last_rise = e[j].t;
        }
        last_word = e[j].gates;
    }
    srm_real_t v[SRM_SIM_MAX_PHASES];
    float on_u[SRM_SIM_MAX_PHASES], on_l[SRM_SIM_MAX_PHASES];
    uint32_t c_ga = ARM_DWT_CYCCNT;
    srm_gate_avg_window(&ga, &sim, e, ne, t0, P, pl.psi, v, on_u, on_l);
    c_ga = ARM_DWT_CYCCNT - c_ga;
    if (c_ga > prof_ga) prof_ga = c_ga;
    prof_ga_sum += c_ga;

    const int q = sim.n_phases;
    if (safety_run()) {
        if (cap_wants_sample()) {
            hil_sample_t s;
            memset(&s, 0, sizeof s);
            s.step = (uint32_t)n_step;
            for (int k = 0; k < q; k++) {
                s.i[k] = emu_sat16(pl.cur[k] * inv_i);
                s.psi[k] = emu_sat16(pl.psi[k] * inv_psi);
                s.v[k] = emu_sat16(v[k] * inv_v);
            }
            s.torque = emu_sat16(pl.ttot * inv_t);
            const double turns = pl.theta * (1.0 / EMU_TWO_PI);
            s.theta = (uint16_t)((uint32_t)((turns - floor(turns)) * 65536.0) & 0xFFFF);
            s.omega = emu_sat16(pl.omega * inv_w);
            s.gates = ga.cmd;
            cap_push(&s);
        }
        w.steps++;
        w.t_sum += pl.ttot;
        if (pl.ttot < w.t_min) w.t_min = pl.ttot;
        if (pl.ttot > w.t_max) w.t_max = pl.ttot;
        for (int k = 0; k < q; k++) w.i2[k] += pl.cur[k] * pl.cur[k];
        uint32_t c_pl = ARM_DWT_CYCCNT;
        srm_plant_step(&pl, &sim, &tab, v, (double)n_step * EMU_DT, n_step);
        c_pl = ARM_DWT_CYCCNT - c_pl;
        if (c_pl > prof_pl) prof_pl = c_pl;
        prof_pl_sum += c_pl;
        n_step++;
        emu_outputs_update(&pl, v);
        if (ne) {
            w.lat_sum += emu_clock_extend(clk, ARM_DWT_CYCCNT) - e[ne - 1].t;
            w.lat_n++;
        }
    } else {
        emu_outputs_zero();
    }

    const uint32_t ov = g_edges.overflows;
    if (ov != edge_overflows_seen) {
        overruns += ov - edge_overflows_seen;
        edge_overflows_seen = ov;
        fault = true;
    }
    const uint64_t end = emu_clock_extend(clk, ARM_DWT_CYCCNT);
    const uint32_t exec = (uint32_t)(end - clk);
    if (exec > step_max) step_max = exec;
    prof_exec_sum += exec;
    prof_n++;
    if (exec > P) {          // the step took longer than its period
        overruns++;
        fault = true;
    }
    if (end > t1 + (uint64_t)EMU_OVERLOAD_STEPS * P) {     // persistently behind: stop before USB starves
        timer.end();
        running = false;
        selftest_settle();
        overloaded = true;
        safety_ready(false);
        emu_outputs_zero();
        cap_abort();
        return;
    }
    safety_ready(!fault);
    w.calls++;
    w.exec_sum += exec;
    if (w.calls >= EMU_STATS_STEPS) publish();
}

static bool finite_nonneg(float x) { return isfinite(x) && x >= 0.0f; }

const char *emu_configure(const hil_emu_config_t *c)
{
    if (running) return "config refused: running";
    if (c->n_phases < 1 || c->n_phases > EMU_MAX_PHASES) return "config refused: n_phases must be 1..4";
    if (c->n_rotor_poles < 1) return "config refused: n_rotor_poles";
    if (c->n_theta < 2 || c->n_theta > EMU_MAX_THETA || c->n_psi < 2 || c->n_psi > EMU_MAX_PSI)
        return "config refused: table grid exceeds 180 x 192";
    if (!(c->theta_step > 0) || !(c->psi_step > 0) || !(c->psi_max > 0) || !(c->i_max > 0))
        return "config refused: table steps";
    if (c->mode > 1) return "config refused: mode";
    if (c->mode == 1 && !(c->inertia > 0)) return "config refused: inertia";
    if (!(c->bus_voltage > 0) || !isfinite(c->speed) || !isfinite(c->theta0) || !finite_nonneg(c->resistance))
        return "config refused: bus voltage, speed, theta0 or resistance";
    if (!finite_nonneg(c->dead_time) || !finite_nonneg(c->turn_on_delay) || !finite_nonneg(c->turn_off_delay) ||
        !finite_nonneg(c->v_switch) || !finite_nonneg(c->v_diode))
        return "config refused: converter settings";
    const char *err = outputs_configure(c);
    if (err) return err;
    cfg = *c;
    memset(&sim, 0, sizeof sim);
    sim.resistance = c->resistance;
    sim.bus_voltage = c->bus_voltage;
    sim.dt = EMU_DT;
    sim.speed = c->speed;
    sim.theta0 = c->theta0;
    sim.inertia = c->inertia;
    sim.friction = c->friction;
    sim.load = c->load;
    sim.load_step = c->load_step;
    sim.load_step_time = c->load_step_time;
    sim.v_switch = c->v_switch;
    sim.v_diode = c->v_diode;
    sim.dead_time = c->dead_time;
    sim.turn_on_delay = c->turn_on_delay;
    sim.turn_off_delay = c->turn_off_delay;
    sim.n_phases = c->n_phases;
    sim.n_rotor_poles = c->n_rotor_poles;
    sim.mode = c->mode;
    tab.theta_step = c->theta_step;
    tab.psi_step = c->psi_step;
    tab.psi_max = c->psi_max;
    tab.i_max = c->i_max;
    tab.n_theta = c->n_theta;
    tab.n_psi = c->n_psi;
    tab.current = g_current;
    tab.torque = g_torque;
    tab.w_field = NULL;
    got[0] = got[1] = 0;
    cfg_ok = true;
    return NULL;
}

const char *emu_table_chunk(const hil_table_chunk_t *c)
{
    if (running) return "table refused: running";
    if (!cfg_ok) return "table refused: no config";
    const uint32_t size = cfg.n_theta * cfg.n_psi;
    if (c->which > 1 || c->n > HIL_TABLE_CHUNK_FLOATS || c->offset > size || c->n > size - c->offset)
        return "table refused: chunk outside the grid";
    // Chunks of a table arrive in order: offset 0 starts it again, any other offset continues where the last ended.
    if (c->offset != 0 && c->offset != got[c->which]) return "table refused: chunk out of order";
    memcpy((c->which ? g_torque : g_current) + c->offset, c->data, c->n * sizeof(float));
    got[c->which] = c->offset + c->n;
    return NULL;
}

const char *emu_start(void)
{
    if (running) return "start refused: running";
    if (!cfg_ok) return "start refused: no config";
    const uint32_t size = cfg.n_theta * cfg.n_psi;
    if (got[0] != size || got[1] != size) return "start refused: tables incomplete";
    double tmax = 0;
    for (uint32_t j = 0; j < size; j++) tmax = fmax(tmax, fabs(g_torque[j]));
    i_scale = 2.0f * cfg.i_max / 32767.0f;
    psi_scale = 2.0f * cfg.psi_max / 32767.0f;
    v_scale = 1.25f * (cfg.bus_voltage + 2.0f * cfg.v_diode) / 32767.0f;
    t_scale = (float)(1.25 * (tmax > 0 ? tmax : 1.0) / 32767.0);
    w_scale = fmaxf(2.0f * fabsf(cfg.speed), 100.0f) / 32767.0f;
    inv_i = 1.0f / i_scale;
    inv_psi = 1.0f / psi_scale;
    inv_v = 1.0f / v_scale;
    inv_t = 1.0f / t_scale;
    inv_w = 1.0f / w_scale;
    P = F_CPU_ACTUAL / EMU_STEP_HZ;
    const double f = (double)F_CPU_ACTUAL;
    srm_gate_avg_init(&ga, llround(((double)cfg.dead_time + (double)cfg.turn_on_delay) * f), llround((double)cfg.turn_off_delay * f), 0);
    srm_plant_init(&pl, &sim, &tab);
    outputs_start(&pl);
    selftest_settle();
    NVIC_DISABLE_IRQ(IRQ_GPIO6789);
    emu_edge_reset(&g_edges);
    outputs_trigger_reset();
    NVIC_ENABLE_IRQ(IRQ_GPIO6789);
    edge_overflows_seen = 0;
    last_word = 0;
    last_rise = 0;
    clk = ARM_DWT_CYCCNT;
    n_win = 0;
    n_step = 0;
    armed = fault = false;
    pat_on = false;
    st_pending = st_duty > 0.0f;
    overruns = 0;
    cap_reset_dropped();
    step_max = prof_ga = prof_pl = 0;
    prof_ga_sum = prof_pl_sum = prof_exec_sum = prof_n = 0;
    window_reset();
    pub_new = false;
    running = true;
    safety_ready(true);
    timer.priority(EMU_PRIO_STEP);
    if (!timer.begin(step_isr, 1e6f / EMU_STEP_HZ)) {
        running = false;
        safety_ready(false);
        return "start refused: no timer";
    }
    return NULL;
}

void emu_stop(void)
{
    timer.end();
    running = false;
    selftest_settle();
    safety_ready(false);
    cap_abort();
    emu_outputs_zero();
}

bool emu_running(void) { return running; }

bool emu_take_overload(void)
{
    if (!overloaded) return false;
    overloaded = false;
    return true;
}

void emu_set_selftest(float duty)
{
    duty = duty > 1.0f ? 1.0f : duty > 0.0f ? duty : 0.0f;
    st_duty = duty;
    // While running, the step interrupt is the only producer of edges until it has ended the pattern, so it clears
    // the flag itself.
    if (duty > 0.0f || !running) g_selftest = duty > 0.0f;
    if (running) st_pending = true;
}

void emu_set_selftest_phases(unsigned mask)
{
    mask &= 0x0F;
    st_word = (uint16_t)(mask | mask << 8);
}

bool emu_live_take(hil_live_emu_t *out)
{
    if (!pub_new) return false;
    pub_new = false;
    *out = pub[pub_idx];
    return true;
}

hil_capture_hdr_t emu_capture_header(uint32_t n_steps)
{
    hil_capture_hdr_t h;
    h.dt = (float)EMU_DT;
    h.i_scale = i_scale;
    h.psi_scale = psi_scale;
    h.v_scale = v_scale;
    h.t_scale = t_scale;
    h.omega_scale = w_scale;
    h.n_steps = n_steps;
    h.n_phases = cfg.n_phases;
    return h;
}

uint32_t emu_capture_default_steps(void) { return cfg.capture_steps; }
uint32_t emu_overruns(void) { return overruns; }
void emu_profile(uint32_t *ga, uint32_t *plant)
{
    *ga = prof_ga;
    *plant = prof_pl;
    ga[1] = prof_n ? (uint32_t)(prof_ga_sum / prof_n) : 0;
    plant[1] = prof_n ? (uint32_t)(prof_pl_sum / prof_n) : 0;
    ga[2] = prof_n ? (uint32_t)(prof_exec_sum / prof_n) : 0;
}
void emu_output_fault(void)
{
    overruns++;
    fault = true;
}

float emu_step_max_us(void) { return (float)(step_max / (double)F_CPU_ACTUAL * 1e6); }
