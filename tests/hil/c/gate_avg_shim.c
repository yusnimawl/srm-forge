/* Thin exports of the gate-edge averager and a linear one-phase plant for the tests. */
#include <string.h>

#include "srm_gate_avg.h"

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

static void make_cfg(srm_sim_config_t *c, int q, double bus, double vs, double vd)
{
    memset(c, 0, sizeof *c);
    c->n_phases = q;
    c->bus_voltage = bus;
    c->v_switch = vs;
    c->v_diode = vd;
}

/* Runs n_windows consecutive windows of dt ticks over the sorted edge list. current is n_windows x q. */
EXPORT int gate_avg_windows(int q, double bus, double vs, double vd, int64_t rise, int64_t fall, uint16_t initial,
                            int n_edges, const uint64_t *edge_t, const uint16_t *edge_g, int n_windows, uint64_t dt,
                            const double *current, double *v_out, float *on_u, float *on_l)
{
    srm_sim_config_t c;
    srm_gate_avg_t g;
    srm_edge_t edges[4096];
    if (n_edges > 4096) return -1;
    for (int i = 0; i < n_edges; i++) {
        edges[i].t = edge_t[i];
        edges[i].gates = edge_g[i];
    }
    make_cfg(&c, q, bus, vs, vd);
    srm_gate_avg_init(&g, rise, fall, initial);
    int e = 0;
    for (int w = 0; w < n_windows; w++) {
        uint64_t t0 = (uint64_t)w * dt;
        int first = e;
        while (e < n_edges && edges[e].t < t0 + dt) e++;
        srm_gate_avg_window(&g, &c, edges + first, e - first, t0, dt, current + (size_t)w * q, v_out + (size_t)w * q,
                            on_u + (size_t)w * q, on_l + (size_t)w * q);
    }
    return 0;
}

/* Both switches off from a flux of psi0 with the plant stepping on the averaged voltage; out = {min psi, min
   current, final psi, final current}. The table is linear, i = psi / L. */
EXPORT void gate_avg_plant_off(double psi0, double inductance, int n_steps, double *out)
{
    enum { NP = 16 };
    static srm_table_t cur[NP], trq[NP];
    srm_sim_config_t c;
    srm_sim_tables_t t;
    srm_plant_t p;
    srm_gate_avg_t g;
    double v[SRM_SIM_MAX_PHASES], current[SRM_SIM_MAX_PHASES];
    float ou[SRM_SIM_MAX_PHASES], ol[SRM_SIM_MAX_PHASES];
    make_cfg(&c, 1, 48.0, 1.0, 1.0);
    c.n_rotor_poles = 6;
    c.resistance = 0.5;
    c.dt = 5e-6;
    c.mode = 1;
    c.inertia = 1.0;
    for (int k = 0; k < NP; k++) {
        cur[k] = (srm_table_t)(0.01 * k / inductance);
        trq[k] = 0;
    }
    memset(&t, 0, sizeof t);
    t.theta_step = 1.0;
    t.psi_step = 0.01;
    t.psi_max = 0.01 * (NP - 1);
    t.n_theta = 1;
    t.n_psi = NP;
    t.current = cur;
    t.torque = trq;
    srm_plant_init(&p, &c, &t);
    p.psi[0] = psi0;
    srm_plant_eval(&c, &t, p.theta, p.psi, p.cur, p.trq, p.wf);
    srm_gate_avg_init(&g, 0, 0, 0);
    out[0] = p.psi[0];
    out[1] = p.cur[0];
    for (int n = 0; n < n_steps; n++) {
        current[0] = p.cur[0];
        srm_gate_avg_window(&g, &c, NULL, 0, (uint64_t)n * 10, 10, current, v, ou, ol);
        srm_plant_step(&p, &c, &t, v, n * c.dt, n);
        if (p.psi[0] < out[0]) out[0] = p.psi[0];
        if (p.cur[0] < out[1]) out[1] = p.cur[0];
    }
    out[2] = p.psi[0];
    out[3] = p.cur[0];
}
