#include "srm_gate_avg.h"

void srm_gate_avg_init(srm_gate_avg_t *g, int64_t rise_ticks, int64_t fall_ticks, uint16_t initial)
{
    g->cmd = g->eff = initial;
    for (int s = 0; s < 16; s++) g->pending_t[s] = 0;
    g->pending_valid = 0;
    g->cache_ticks = 0;
    g->rise_ticks = rise_ticks;
    g->fall_ticks = fall_ticks;
}

/* A new command word: a switch commanded to its effective level drops any pending change, otherwise the delay
   restarts from this tick. */
static void command(srm_gate_avg_t *g, uint16_t word, uint64_t t)
{
    unsigned changed = (uint16_t)(word ^ g->cmd);
    g->cmd = word;
    while (changed) {
        int s = __builtin_ctz(changed);
        uint16_t bit = (uint16_t)(1u << s);
        changed &= changed - 1u;
        if (((word ^ g->eff) & bit) == 0) {
            g->pending_valid &= (uint16_t)~bit;
        } else {
            int64_t d = (word & bit) ? g->rise_ticks : g->fall_ticks;
            g->pending_t[s] = t + (uint64_t)d;
            g->pending_valid |= bit;
        }
    }
}

/* Earliest pending tick, or UINT64_MAX when none. */
static uint64_t next_pending(const srm_gate_avg_t *g)
{
    uint64_t best = UINT64_MAX;
    for (unsigned m = g->pending_valid; m; m &= m - 1u) {
        int s = __builtin_ctz(m);
        if (g->pending_t[s] < best) best = g->pending_t[s];
    }
    return best;
}

static void mature(srm_gate_avg_t *g, uint64_t t)
{
    for (unsigned m = g->pending_valid; m; m &= m - 1u) {
        int s = __builtin_ctz(m);
        uint16_t bit = (uint16_t)(1u << s);
        if (g->pending_t[s] <= t) {
            g->eff = (uint16_t)((g->eff & ~bit) | (g->cmd & bit));
            g->pending_valid &= (uint16_t)~bit;
        }
    }
}

/* Winding voltage for the effective switch states, given whether the winding conducts (positive flux); the same
   values as srm_ahb_voltage. */
static inline srm_real_t ahb(const srm_gate_avg_t *g, int u, int l, int conducting)
{
    if (u && l) return g->v_on;
    if (u || l) return conducting ? g->v_free : SRM_REAL(0.0);
    return conducting ? g->v_demag : SRM_REAL(0.0);
}

/* Advances the running fluxes psi over span ticks at the held effective gates. The winding conducts the freewheel
   and demagnetising paths only while its flux is positive, and the flux stops at zero. */
static void accumulate(const srm_gate_avg_t *g, const srm_sim_config_t *c, srm_real_t span, srm_real_t *psi,
                       float *on_upper, float *on_lower)
{
    const srm_real_t tau = span * g->tick_s;
    for (int k = 0; k < c->n_phases; k++) {
        int u = (g->eff >> k) & 1, l = (g->eff >> (8 + k)) & 1;
        if (!u && !l && !(psi[k] > SRM_REAL(0.0))) continue;      /* idle winding: no voltage, no flux change */
        srm_real_t v = ahb(g, u, l, psi[k] > SRM_REAL(0.0));
        if (v >= SRM_REAL(0.0) || psi[k] > -v * tau) psi[k] += v * tau;
        else psi[k] = SRM_REAL(0.0);
        on_upper[k] += (float)((srm_real_t)u * span);
        on_lower[k] += (float)((srm_real_t)l * span);
    }
}

/* A tick count in the real type; a 32-bit conversion is one instruction on the Cortex-M7, a 64-bit one a library
   call. */
static srm_real_t span_ticks(uint64_t n) { return n <= UINT32_MAX ? (srm_real_t)(uint32_t)n : (srm_real_t)n; }

void srm_gate_avg_window(srm_gate_avg_t *g, const srm_sim_config_t *c, const srm_edge_t *edges, int n, uint64_t t0,
                         uint64_t dt, const srm_real_t *psi0, srm_real_t *v_out, float *on_upper, float *on_lower)
{
    const uint64_t t1 = t0 + dt;
    uint64_t now = t0;
    int e = 0;
    if (g->cache_ticks != dt || g->cache_dt != c->dt || g->cache_cfg != (const void *)c) {
        g->cache_ticks = dt;
        g->cache_dt = c->dt;
        g->cache_cfg = c;
        g->tick_s = (srm_real_t)(c->dt / (double)span_ticks(dt));
        g->inv_ticks = SRM_REAL(1.0) / span_ticks(dt);
        g->dt_r = (srm_real_t)c->dt;
        g->v_on = (srm_real_t)(c->bus_voltage - 2.0 * c->v_switch);
        g->v_free = (srm_real_t)(-(c->v_switch + c->v_diode));
        g->v_demag = (srm_real_t)(-(c->bus_voltage + 2.0 * c->v_diode));
    }
#ifndef SRM_GATE_AVG_NO_FAST_PATH     /* defined only by the test that compares both paths */
    if (n == 0 && !g->pending_valid) {
        /* No edge and no pending change: one segment over the whole window. The same arithmetic as accumulate and
           the closing loop below, fused. */
        const srm_real_t span = span_ticks(dt), tau = span * g->tick_s, inv = g->inv_ticks;
        for (int k = 0; k < c->n_phases; k++) {
            int u = (g->eff >> k) & 1, l = (g->eff >> (8 + k)) & 1;
            srm_real_t psi = psi0[k];
            float ou = 0.0f, ol = 0.0f;
            if (u || l || psi > SRM_REAL(0.0)) {
                srm_real_t v = ahb(g, u, l, psi > SRM_REAL(0.0));
                if (v >= SRM_REAL(0.0) || psi > -v * tau) psi += v * tau;
                else psi = SRM_REAL(0.0);
                ou += (float)((srm_real_t)u * span);
                ol += (float)((srm_real_t)l * span);
            }
            v_out[k] = (psi - psi0[k]) / g->dt_r;
            on_upper[k] = (float)((srm_real_t)ou * inv);
            on_lower[k] = (float)((srm_real_t)ol * inv);
        }
        return;
    }
#endif
    srm_real_t psi[SRM_SIM_MAX_PHASES];
    for (int k = 0; k < c->n_phases; k++) {
        psi[k] = psi0[k];
        on_upper[k] = on_lower[k] = 0.0f;
    }

    for (;;) {
        uint64_t te = e < n ? edges[e].t : UINT64_MAX;
        uint64_t tp = next_pending(g);
        uint64_t ts = te < tp ? te : tp;      /* an edge at the same tick as a maturing change comes first */
        if (ts >= t1) break;
        if (ts < now) ts = now;
        if (ts > now) accumulate(g, c, span_ticks(ts - now), psi, on_upper, on_lower);
        now = ts;
        if (te <= tp) {
            while (e < n && edges[e].t <= ts) command(g, edges[e++].gates, ts);
        }
        mature(g, ts);
    }
    if (t1 > now) accumulate(g, c, span_ticks(t1 - now), psi, on_upper, on_lower);

    const srm_real_t inv = g->inv_ticks;
    for (int k = 0; k < c->n_phases; k++) {
        v_out[k] = (psi[k] - psi0[k]) / g->dt_r;
        on_upper[k] = (float)((srm_real_t)on_upper[k] * inv);
        on_lower[k] = (float)((srm_real_t)on_lower[k] * inv);
    }
}
