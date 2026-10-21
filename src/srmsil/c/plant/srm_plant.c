#include <math.h>
#include <string.h>

#include "srm_plant.h"

#define TWO_PI 6.283185307179586476925286766559

static double eps(const srm_sim_config_t *c)
{
    return TWO_PI / ((double)c->n_phases * (double)c->n_rotor_poles);
}

#ifdef SRM_TABLE_FLOAT
static void lookup_constants(srm_plant_t *k, const srm_sim_config_t *c, const srm_sim_tables_t *t)
{
    k->k_eps = eps(c);
    k->k_period = t->theta_step * (double)t->n_theta;
    k->k_inv_period = 1.0 / k->k_period;
    k->k_inv_theta = 1.0f / (float)t->theta_step;
    k->k_inv_psi = 1.0f / (float)t->psi_step;
}

/* Float-table build: the rotor angle is wrapped once, each phase's angle is shifted within the table period, and
   phases at zero flux skip the lookup (see srm_motor_eval). */
static double eval_k(const srm_plant_t *k, const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta,
                     const double *psi, double *i, double *trq, double *w)
{
    double sum = 0.0, th0 = NAN;
    for (int q = 0; q < c->n_phases; q++) {
        if (!(psi[q] > 0.0) || !isfinite(psi[q])) {
            i[q] = trq[q] = w[q] = 0.0;
            continue;
        }
        if (th0 != th0) {
            th0 = theta - k->k_period * floor(theta * k->k_inv_period);
            if (!isfinite(th0)) th0 = 0.0;
        }
        double th = th0 - (double)q * k->k_eps;
        while (th < 0.0) th += k->k_period;
        srm_motor_lookup_f(t, (float)th * k->k_inv_theta, (float)psi[q] * k->k_inv_psi, &i[q], &trq[q], &w[q]);
        sum += trq[q];
    }
    return sum;
}

double srm_plant_eval(const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta, const double *psi,
                      double *i, double *trq, double *w)
{
    srm_plant_t k;
    lookup_constants(&k, c, t);
    return eval_k(&k, c, t, theta, psi, i, trq, w);
}
#define EVAL(c, t, theta, psi, i, trq, w) eval_k(p, c, t, theta, psi, i, trq, w)
#else
double srm_plant_eval(const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta, const double *psi,
                      double *i, double *trq, double *w)
{
    double sum = 0.0;
    const double e = eps(c);
    for (int k = 0; k < c->n_phases; k++) {
        srm_motor_eval(t, theta - (double)k * e, psi[k], &i[k], &trq[k], &w[k]);
        sum += trq[k];
    }
    return sum;
}
#define EVAL(c, t, theta, psi, i, trq, w) srm_plant_eval(c, t, theta, psi, i, trq, w)
#endif

void srm_plant_init(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t)
{
    memset(p, 0, sizeof *p);
    p->theta = c->theta0;
    p->omega = c->speed;
#ifdef SRM_TABLE_FLOAT
    lookup_constants(p, c, t);
#endif
    p->ttot = EVAL(c, t, p->theta, p->psi, p->cur, p->trq, p->wf);
}

static double load_torque(const srm_sim_config_t *c, double t)
{
    return c->load + (t >= c->load_step_time ? c->load_step : 0.0);
}

void srm_plant_step(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t, const double *v,
                    double t_now, int64_t n)
{
    const int q = c->n_phases;
    const double dt = c->dt, R = c->resistance;
    const int dynamic = c->mode == 1;
    const double load0 = load_torque(c, t_now), load1 = load_torque(c, t_now + dt);
    double k1[SRM_SIM_MAX_PHASES], psi_p[SRM_SIM_MAX_PHASES], i_p[SRM_SIM_MAX_PHASES], t_p[SRM_SIM_MAX_PHASES],
        w_p[SRM_SIM_MAX_PHASES];
    const double a1 = dynamic ? (p->ttot - c->friction * p->omega - load0) / c->inertia : 0.0;
    for (int k = 0; k < q; k++) {
        k1[k] = v[k] - R * p->cur[k];
        psi_p[k] = p->psi[k] + dt * k1[k];
    }
    const double omega_p = p->omega + dt * a1;
    const double tt_p = EVAL(c, t, p->theta + dt * p->omega, psi_p, i_p, t_p, w_p);
    const double a2 = dynamic ? (tt_p - c->friction * omega_p - load1) / c->inertia : 0.0;
    for (int k = 0; k < q; k++) {
        double psi = p->psi[k] + 0.5 * dt * (k1[k] + (v[k] - R * i_p[k]));
        p->psi[k] = psi > 0.0 ? psi : 0.0;
    }
    const double theta_new = dynamic ? p->theta + 0.5 * dt * (p->omega + omega_p)
                                     : c->theta0 + c->speed * (double)(n + 1) * dt;
    const double omega_new = p->omega + 0.5 * dt * (a1 + a2);
    p->ttot = EVAL(c, t, theta_new, p->psi, p->cur, p->trq, p->wf);
    p->theta = theta_new;
    p->omega = omega_new;
}

double srm_ahb_voltage(const srm_sim_config_t *c, int upper, int lower, double current)
{
    if (upper && lower) return c->bus_voltage - 2.0 * c->v_switch;
    if (upper || lower) return current > 0.0 ? -(c->v_switch + c->v_diode) : 0.0;
    return current > 0.0 ? -(c->bus_voltage + 2.0 * c->v_diode) : 0.0;
}
