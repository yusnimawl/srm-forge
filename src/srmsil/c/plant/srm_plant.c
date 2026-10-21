#include <math.h>
#include <string.h>

#include "srm_plant.h"

#define TWO_PI 6.283185307179586476925286766559

static double eps(const srm_sim_config_t *c)
{
    return TWO_PI / ((double)c->n_phases * (double)c->n_rotor_poles);
}

static void plant_constants(srm_plant_t *k, const srm_sim_config_t *c, const srm_sim_tables_t *t)
{
    k->k_dt = (srm_real_t)c->dt;
    k->k_r = (srm_real_t)c->resistance;
    k->k_inertia = (srm_real_t)c->inertia;
    k->k_friction = (srm_real_t)c->friction;
    k->k_load = (srm_real_t)c->load;
    k->k_load_step = (srm_real_t)c->load_step;
    k->k_eps = eps(c);
    k->k_period = t->theta_step * (double)t->n_theta;
    k->k_inv_period = 1.0 / k->k_period;
    k->k_inv_theta = 1.0f / (float)t->theta_step;
    k->k_inv_psi = 1.0f / (float)t->psi_step;
}

#ifdef SRM_TABLE_FLOAT
/* Float-table build: the rotor angle is wrapped once (in double), each phase's angle is shifted within the table
   period in float, and phases at zero flux skip the lookup (see srm_motor_eval). */
static float eval_k(const srm_plant_t *k, const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta,
                    const float *psi, float *i, float *trq, float *w)
{
    float sum = 0.0f, th0 = -1.0f;
    const float period = (float)k->k_period, e = (float)k->k_eps;
    for (int q = 0; q < c->n_phases; q++) {
        if (!(psi[q] > 0.0f && psi[q] < INFINITY)) {      /* zero, negative, infinite or NaN flux */
            i[q] = trq[q] = w[q] = 0.0f;
            continue;
        }
        if (th0 < 0.0f) {
            double th = theta - k->k_period * floor(theta * k->k_inv_period);
            th0 = isfinite(th) && th >= 0.0 ? (float)th : 0.0f;
        }
        float th = th0 - (float)q * e;
        while (th < 0.0f) th += period;
        srm_motor_lookup_f(t, th * k->k_inv_theta, psi[q] * k->k_inv_psi, &i[q], &trq[q], &w[q]);
        sum += trq[q];
    }
    return sum;
}

float srm_plant_eval(const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta, const float *psi, float *i,
                     float *trq, float *w)
{
    srm_plant_t k;
    plant_constants(&k, c, t);
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
    p->omega = (srm_real_t)c->speed;
    plant_constants(p, c, t);
    p->ttot = EVAL(c, t, p->theta, p->psi, p->cur, p->trq, p->wf);
}

/* A step count as double; a 32-bit conversion is one instruction on the Cortex-M7, a 64-bit one a library call. */
static double step_count(int64_t n) { return (n >= INT32_MIN && n <= INT32_MAX) ? (double)(int32_t)n : (double)n; }

static srm_real_t load_torque(const srm_plant_t *p, const srm_sim_config_t *c, double t)
{
    return p->k_load + (t >= c->load_step_time ? p->k_load_step : SRM_REAL(0.0));
}

void srm_plant_step(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t, const srm_real_t *v,
                    double t_now, int64_t n)
{
    const int q = c->n_phases;
    const srm_real_t dt = p->k_dt, R = p->k_r;
    const int dynamic = c->mode == 1;
    const srm_real_t load0 = load_torque(p, c, t_now), load1 = load_torque(p, c, t_now + c->dt);
    srm_real_t k1[SRM_SIM_MAX_PHASES], psi_p[SRM_SIM_MAX_PHASES], i_p[SRM_SIM_MAX_PHASES], t_p[SRM_SIM_MAX_PHASES],
        w_p[SRM_SIM_MAX_PHASES];
    const srm_real_t a1 = dynamic ? (p->ttot - p->k_friction * p->omega - load0) / p->k_inertia : SRM_REAL(0.0);
    for (int k = 0; k < q; k++) {
        k1[k] = v[k] - R * p->cur[k];
        psi_p[k] = p->psi[k] + dt * k1[k];
    }
    const srm_real_t omega_p = p->omega + dt * a1;
    const srm_real_t tt_p = EVAL(c, t, p->theta + (double)(dt * p->omega), psi_p, i_p, t_p, w_p);
    const srm_real_t a2 = dynamic ? (tt_p - p->k_friction * omega_p - load1) / p->k_inertia : SRM_REAL(0.0);
    for (int k = 0; k < q; k++) {
        srm_real_t psi = p->psi[k] + SRM_REAL(0.5) * dt * (k1[k] + (v[k] - R * i_p[k]));
        p->psi[k] = psi > SRM_REAL(0.0) ? psi : SRM_REAL(0.0);
    }
    const double theta_new = dynamic ? p->theta + (double)(SRM_REAL(0.5) * dt * (p->omega + omega_p))
                                     : c->theta0 + c->speed * step_count(n + 1) * c->dt;
    const srm_real_t omega_new = p->omega + SRM_REAL(0.5) * dt * (a1 + a2);
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
