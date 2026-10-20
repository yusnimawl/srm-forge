#include <math.h>
#include <string.h>

#include "srm_plant.h"

#define TWO_PI 6.283185307179586476925286766559

static double eps(const srm_sim_config_t *c)
{
    return TWO_PI / ((double)c->n_phases * (double)c->n_rotor_poles);
}

double srm_plant_eval(const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta, const double *psi,
                      double *i, double *trq, double *w)
{
    double sum = 0.0;
    for (int k = 0; k < c->n_phases; k++) {
        srm_motor_eval(t, theta - (double)k * eps(c), psi[k], &i[k], &trq[k], &w[k]);
        sum += trq[k];
    }
    return sum;
}

void srm_plant_init(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t)
{
    memset(p, 0, sizeof *p);
    p->theta = c->theta0;
    p->omega = c->speed;
    p->ttot = srm_plant_eval(c, t, p->theta, p->psi, p->cur, p->trq, p->wf);
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
    const double tt_p = srm_plant_eval(c, t, p->theta + dt * p->omega, psi_p, i_p, t_p, w_p);
    const double a2 = dynamic ? (tt_p - c->friction * omega_p - load1) / c->inertia : 0.0;
    for (int k = 0; k < q; k++) {
        double psi = p->psi[k] + 0.5 * dt * (k1[k] + (v[k] - R * i_p[k]));
        p->psi[k] = psi > 0.0 ? psi : 0.0;
    }
    const double theta_new = dynamic ? p->theta + 0.5 * dt * (p->omega + omega_p)
                                     : c->theta0 + c->speed * (double)(n + 1) * dt;
    const double omega_new = p->omega + 0.5 * dt * (a1 + a2);
    p->ttot = srm_plant_eval(c, t, theta_new, p->psi, p->cur, p->trq, p->wf);
    p->theta = theta_new;
    p->omega = omega_new;
}

double srm_ahb_voltage(const srm_sim_config_t *c, int upper, int lower, double current)
{
    if (upper && lower) return c->bus_voltage - 2.0 * c->v_switch;
    if (upper || lower) return current > 0.0 ? -(c->v_switch + c->v_diode) : 0.0;
    return current > 0.0 ? -(c->bus_voltage + 2.0 * c->v_diode) : 0.0;
}
