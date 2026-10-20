#include "srm_gate_avg.h"

void srm_gate_avg_init(srm_gate_avg_t *g, int64_t rise_ticks, int64_t fall_ticks, uint16_t initial)
{
    g->cmd = g->eff = initial;
    for (int s = 0; s < 16; s++) g->pending_t[s] = 0;
    g->pending_valid = 0;
    g->rise_ticks = rise_ticks;
    g->fall_ticks = fall_ticks;
}

/* A new command word: a switch commanded to its effective level drops any pending change, otherwise the delay
   restarts from this tick. */
static void command(srm_gate_avg_t *g, uint16_t word, uint64_t t)
{
    uint16_t changed = (uint16_t)(word ^ g->cmd);
    g->cmd = word;
    for (int s = 0; s < 16; s++) {
        uint16_t bit = (uint16_t)(1u << s);
        if (!(changed & bit)) continue;
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
    for (int s = 0; s < 16; s++)
        if ((g->pending_valid & (1u << s)) && g->pending_t[s] < best) best = g->pending_t[s];
    return best;
}

static void mature(srm_gate_avg_t *g, uint64_t t)
{
    for (int s = 0; s < 16; s++) {
        uint16_t bit = (uint16_t)(1u << s);
        if ((g->pending_valid & bit) && g->pending_t[s] <= t) {
            g->eff = (uint16_t)((g->eff & ~bit) | (g->cmd & bit));
            g->pending_valid &= (uint16_t)~bit;
        }
    }
}

/* Advances the running fluxes psi over span ticks of tick_s seconds at the held effective gates. The winding conducts
   the freewheel and demagnetising paths only while its flux is positive, and the flux stops at zero. */
static void accumulate(const srm_gate_avg_t *g, const srm_sim_config_t *c, double tick_s, double span, double *psi,
                       float *on_upper, float *on_lower)
{
    for (int k = 0; k < c->n_phases; k++) {
        int u = (g->eff >> k) & 1, l = (g->eff >> (8 + k)) & 1;
        double tau = span * tick_s;
        double v = srm_ahb_voltage(c, u, l, psi[k] > 0.0 ? 1.0 : 0.0);
        if (v >= 0.0 || psi[k] > -v * tau) psi[k] += v * tau;
        else psi[k] = 0.0;
        on_upper[k] += (float)(u * span);
        on_lower[k] += (float)(l * span);
    }
}

void srm_gate_avg_window(srm_gate_avg_t *g, const srm_sim_config_t *c, const srm_edge_t *edges, int n, uint64_t t0,
                         uint64_t dt, const double *psi0, double *v_out, float *on_upper, float *on_lower)
{
    const uint64_t t1 = t0 + dt;
    uint64_t now = t0;
    int e = 0;
    const double tick_s = c->dt / (double)dt;
    double psi[SRM_SIM_MAX_PHASES];
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
        if (ts > now) accumulate(g, c, tick_s, (double)(ts - now), psi, on_upper, on_lower);
        now = ts;
        if (te <= tp) {
            while (e < n && edges[e].t <= ts) command(g, edges[e++].gates, ts);
        }
        mature(g, ts);
    }
    if (t1 > now) accumulate(g, c, tick_s, (double)(t1 - now), psi, on_upper, on_lower);

    const double inv = 1.0 / (double)dt;
    for (int k = 0; k < c->n_phases; k++) {
        v_out[k] = (psi[k] - psi0[k]) / c->dt;
        on_upper[k] = (float)(on_upper[k] * inv);
        on_lower[k] = (float)(on_lower[k] * inv);
    }
}
