/* Open-loop model of the real-time emulator: the plant stepping at cfg->dt on the time-averaged winding voltages
   of a gate-edge list. Built with SRM_TABLE_FLOAT it uses the same table type as the Teensy. */
#include <math.h>
#include <string.h>

#include "srm_gate_avg.h"
#include "srm_sim.h"

/* This library does not contain srm_sim.c, so it answers the ABI checks of srmsil._abi.bind_tables itself. */
SRM_SIM_API int srm_sim_abi(void) { return SRM_SIM_ABI; }
SRM_SIM_API size_t srm_sim_sizeof_config(void) { return sizeof(srm_sim_config_t); }
SRM_SIM_API size_t srm_sim_sizeof_tables(void) { return sizeof(srm_sim_tables_t); }
SRM_SIM_API size_t srm_sim_sizeof_summary(void) { return sizeof(srm_sim_summary_t); }

/* i_trace, if not NULL, receives the phase currents at the start of every step (n_steps x n_phases, step-major).
   0 ok, -1 bad configuration (dynamic mode, a step that is not a whole number of ticks, ...) */
SRM_SIM_API int srm_emu_run(const srm_sim_config_t *cfg, const srm_sim_tables_t *tab, const srm_edge_t *edges,
                            int64_t n_edges, double tick_s, srm_sim_summary_t *sum, double *i_trace)
{
    const int q = cfg->n_phases;
    if (q < 1 || q > SRM_SIM_MAX_PHASES || cfg->n_steps < 1 || !(cfg->dt > 0.0) || !(tick_s > 0.0) ||
        cfg->mode != 0 || n_edges < 0)
        return -1;
    const int64_t per_step = (int64_t)llround(cfg->dt / tick_s);
    if (per_step < 1 || fabs((double)per_step * tick_s - cfg->dt) > 1.0e-6 * cfg->dt) return -1;

    srm_gate_avg_t g;
    srm_gate_avg_init(&g, (int64_t)llround((cfg->dead_time + cfg->turn_on_delay) / tick_s),
                      (int64_t)llround(cfg->turn_off_delay / tick_s), 0);
    memset(sum, 0, sizeof *sum);
    sum->torque_min = (double)INFINITY;
    sum->torque_max = -(double)INFINITY;

    srm_plant_t pl;
    const double dt = cfg->dt, R = cfg->resistance;
    srm_plant_init(&pl, cfg, tab);
    for (int k = 0; k < q; k++) sum->w_field_start += (double)pl.wf[k];

    const int64_t window_start = cfg->n_steps / 2;
    int64_t e = 0;
    for (int64_t n = 0; n < cfg->n_steps; n++) {
        const uint64_t t0 = (uint64_t)n * (uint64_t)per_step;
        int64_t first = e;
        while (e < n_edges && edges[e].t < t0 + (uint64_t)per_step) e++;
        srm_real_t v[SRM_SIM_MAX_PHASES];
        double pin = 0.0, cu = 0.0;
        float on_u[SRM_SIM_MAX_PHASES], on_l[SRM_SIM_MAX_PHASES];
        srm_gate_avg_window(&g, cfg, edges + first, (int)(e - first), t0, (uint64_t)per_step, pl.psi, v, on_u, on_l);
        double cur[SRM_SIM_MAX_PHASES];
        for (int k = 0; k < q; k++) cur[k] = (double)pl.cur[k];
        if (i_trace) memcpy(i_trace + (size_t)n * (size_t)q, cur, (size_t)q * sizeof(double));
        int beyond = 0;
        for (int k = 0; k < q; k++) {
            pin += (double)v[k] * cur[k];
            cu += R * cur[k] * cur[k];
            if (cur[k] > tab->i_max || (double)pl.psi[k] > tab->psi_max) beyond = 1;
        }
        sum->beyond_map_steps += beyond;
        const double ttot = (double)pl.ttot, pmech = ttot * (double)pl.omega;
        if (n >= window_start) {
            sum->window_steps++;
            sum->torque_sum += ttot;
            if (ttot < sum->torque_min) sum->torque_min = ttot;
            if (ttot > sum->torque_max) sum->torque_max = ttot;
            sum->copper_sum += cu;
            sum->power_in_sum += pin;
            sum->power_mech_sum += pmech;
            for (int k = 0; k < q; k++) sum->i2_sum[k] += cur[k] * cur[k];
        }
        srm_plant_step(&pl, cfg, tab, v, (double)n * dt, n);
        for (int k = 0; k < q; k++) {
            const double c1 = (double)pl.cur[k];
            sum->energy_in += dt * (double)v[k] * 0.5 * (cur[k] + c1);
            sum->energy_copper += dt * R * 0.5 * (cur[k] * cur[k] + c1 * c1);
        }
        sum->energy_mech += dt * 0.5 * (pmech + (double)pl.ttot * (double)pl.omega);
    }
    for (int k = 0; k < q; k++) sum->w_field_end += (double)pl.wf[k];
    return 0;
}
