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

/* A segment of a window: its length in ticks, that length in seconds and the effective gates held over it. */
typedef struct {
    srm_real_t span, tau;
    uint16_t eff;
} segment_t;

#define SEG_CHUNK 16      /* segments advanced together; a window with more is advanced chunk by chunk */

/* Advances one winding's running flux *psi over the segments in order. The winding conducts the freewheel and
   demagnetising paths only while its flux is positive, and the flux stops at zero. With on set, the ticks each
   switch is on are added to *on_u and *on_l. */
static inline void advance(const srm_gate_avg_t *g, int k, const segment_t *s, int n, srm_real_t *psi, float *on_u,
                           float *on_l, const int on)
{
    srm_real_t p = *psi;
    float ou = on ? *on_u : 0.0f, ol = on ? *on_l : 0.0f;
    for (int i = 0; i < n; i++) {
        int u = (s[i].eff >> k) & 1, l = (s[i].eff >> (8 + k)) & 1;
        if (!u && !l && !(p > SRM_REAL(0.0))) continue;      /* idle winding: no voltage, no flux change */
        srm_real_t v = ahb(g, u, l, p > SRM_REAL(0.0));
        const srm_real_t tau = s[i].tau;
        if (v >= SRM_REAL(0.0) || p > -v * tau) p += v * tau;
        else p = SRM_REAL(0.0);
        if (on) {
            ou += (float)((srm_real_t)u * s[i].span);
            ol += (float)((srm_real_t)l * s[i].span);
        }
    }
    *psi = p;
    if (on) {
        *on_u = ou;
        *on_l = ol;
    }
}

/* Advances every winding from the fluxes src over the n segments into dst (src may be dst); any is the OR of their
   gate words. A winding off in every segment and at zero flux stays as it is. */
static void advance_all(const srm_gate_avg_t *g, const srm_sim_config_t *c, const segment_t *s, int n, uint16_t any,
                        const srm_real_t *src, srm_real_t *dst, float *on_upper, float *on_lower)
{
    for (int k = 0; k < c->n_phases; k++) {
        srm_real_t p = src[k];
        if (any & (0x0101u << k) || p > SRM_REAL(0.0)) {
            if (on_upper) advance(g, k, s, n, &p, &on_upper[k], &on_lower[k], 1);
            else advance(g, k, s, n, &p, NULL, NULL, 0);
        }
        dst[k] = p;
    }
}

/* Ticks from t0 to t: 0 for t at or before t0, w for t w or more ticks after t0. */
static inline uint32_t rel_ticks(uint64_t t, uint64_t t0, uint32_t w)
{
    return t <= t0 ? 0u : t - t0 >= w ? w : (uint32_t)(t - t0);
}

/* A tick count in the real type; a 32-bit conversion is one instruction on the Cortex-M7, a 64-bit one a library
   call. */
static srm_real_t span_ticks(uint64_t n) { return n <= UINT32_MAX ? (srm_real_t)(uint32_t)n : (srm_real_t)n; }

void srm_gate_avg_window(srm_gate_avg_t *g, const srm_sim_config_t *c, const srm_edge_t *edges, int n, uint64_t t0,
                         uint64_t dt, const srm_real_t *psi0, srm_real_t *v_out, float *on_upper, float *on_lower)
{
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
        /* No edge and no pending change: one segment over the whole window. The same arithmetic as advance and the
           closing loops below, fused. */
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
            if (on_upper) {
                on_upper[k] = (float)((srm_real_t)ou * inv);
                on_lower[k] = (float)((srm_real_t)ol * inv);
            }
        }
        return;
    }
#endif
    /* Events at or before t0 (late edges, changes due before the window) take effect at t0, in time order. */
    for (;;) {
        uint64_t te = e < n ? edges[e].t : UINT64_MAX;
        uint64_t tp = next_pending(g);
        if ((te < tp ? te : tp) > t0) break;
        if (te <= tp) {
            while (e < n && edges[e].t <= t0) command(g, edges[e++].gates, t0);
        }
        mature(g, t0);
    }

    /* The rest of the window in ticks after t0 (dt < 2^32): every remaining event is after t0, and an event at or
       after t1 reads as w. The window's segments between edges and maturing changes are collected, then each winding
       is advanced over them: the same per-winding sequence of operations as advancing every winding segment by
       segment. */
    const uint32_t w = (uint32_t)dt;
    uint16_t cmd = g->cmd, eff = g->eff, pv = g->pending_valid;
    uint32_t pr[16];          /* ticks after t0 at which each pending change matures */
    uint32_t tp = w;
    for (unsigned m = pv; m; m &= m - 1u) {
        int s = __builtin_ctz(m);
        pr[s] = rel_ticks(g->pending_t[s], t0, w);
        if (pr[s] < tp) tp = pr[s];
    }
    srm_real_t psi[SRM_SIM_MAX_PHASES];
    const srm_real_t *src = psi0;
    if (on_upper) {
        for (int k = 0; k < c->n_phases; k++) on_upper[k] = on_lower[k] = 0.0f;
    }
    segment_t seg[SEG_CHUNK];
    int ns = 0;
    uint16_t any = 0;
    uint32_t now = 0;
    for (;;) {
        uint32_t te = e < n ? rel_ticks(edges[e].t, t0, w) : w;
        uint32_t ts = te < tp ? te : tp;      /* an edge at the same tick as a maturing change comes first */
        if (ts > now) {
            if (ns == SEG_CHUNK) {
                advance_all(g, c, seg, ns, any, src, psi, on_upper, on_lower);
                src = psi;
                ns = 0;
                any = 0;
            }
            seg[ns].span = (srm_real_t)(ts - now);
            seg[ns].tau = seg[ns].span * g->tick_s;
            seg[ns].eff = eff;
            any |= eff;
            ns++;
            now = ts;
        }
        if (ts >= w) break;
        if (te <= tp) {
            /* new command words: a switch commanded to its effective level drops any pending change, otherwise
               the delay restarts from this tick */
            for (; e < n && rel_ticks(edges[e].t, t0, w) <= now; e++) {
                const uint16_t word = edges[e].gates;
                unsigned changed = (uint16_t)(word ^ cmd);
                cmd = word;
                for (; changed; changed &= changed - 1u) {
                    int s = __builtin_ctz(changed);
                    uint16_t bit = (uint16_t)(1u << s);
                    if (((word ^ eff) & bit) == 0) {
                        pv &= (uint16_t)~bit;
                    } else {
                        int64_t d = (word & bit) ? g->rise_ticks : g->fall_ticks;
                        g->pending_t[s] = t0 + now + (uint64_t)d;
                        pr[s] = rel_ticks(g->pending_t[s], t0, w);
                        pv |= bit;
                    }
                }
            }
        }
        tp = w;
        for (unsigned m = pv; m; m &= m - 1u) {
            int s = __builtin_ctz(m);
            uint16_t bit = (uint16_t)(1u << s);
            if (pr[s] <= now) {
                eff = (uint16_t)((eff & ~bit) | (cmd & bit));
                pv &= (uint16_t)~bit;
            } else if (pr[s] < tp) {
                tp = pr[s];
            }
        }
    }
    g->cmd = cmd;
    g->eff = eff;
    g->pending_valid = pv;
    advance_all(g, c, seg, ns, any, src, psi, on_upper, on_lower);

    for (int k = 0; k < c->n_phases; k++) v_out[k] = (psi[k] - psi0[k]) / g->dt_r;
    if (on_upper) {
        const srm_real_t inv = g->inv_ticks;
        for (int k = 0; k < c->n_phases; k++) {
            on_upper[k] = (float)((srm_real_t)on_upper[k] * inv);
            on_lower[k] = (float)((srm_real_t)on_lower[k] * inv);
        }
    }
}
