#include <math.h>

#include "srm_plant.h"

/* One table row at flux psi: linear in flux, extending the last two columns beyond the grid. */
static void row_eval(const srm_sim_tables_t *tab, int64_t row, double psi, double *i, double *torque, double *w)
{
    int64_t n = tab->n_psi;
    const srm_table_t *ci = tab->current + row * n, *ct = tab->torque + row * n;
    const srm_table_t *cw = tab->w_field ? tab->w_field + row * n : NULL;
    double s = psi / tab->psi_step;
    if (s >= (double)(n - 1)) {
        double d = s - (double)(n - 1);
        *i = ci[n - 1] + d * (ci[n - 1] - ci[n - 2]);
        *torque = ct[n - 1] + d * (ct[n - 1] - ct[n - 2]);
        *w = cw ? cw[n - 1] + 0.5 * d * tab->psi_step * (ci[n - 1] + *i) : 0.0;
        return;
    }
    int64_t k = (int64_t)s;
    double f = s - (double)k;
    *i = ci[k] + f * (ci[k + 1] - ci[k]);
    *torque = ct[k] + f * (ct[k + 1] - ct[k]);
    *w = cw ? cw[k] + f * (cw[k + 1] - cw[k]) : 0.0;
}

void srm_motor_eval(const srm_sim_tables_t *tab, double theta_phase, double psi, double *i, double *torque,
                    double *w)
{
    double period = tab->theta_step * (double)tab->n_theta;
    if (!(psi > 0.0)) psi = 0.0;
    if (!isfinite(psi)) psi = 0.0;
    double th = fmod(theta_phase, period);
    if (!isfinite(th)) th = 0.0;
    if (th < 0.0) th += period;
    double u = th / tab->theta_step;
    int64_t j = (int64_t)u;
    if (j >= tab->n_theta) j = tab->n_theta - 1;
    double f = u - (double)j;
    int64_t j1 = (j + 1 == tab->n_theta) ? 0 : j + 1;
    double i0, t0, w0, i1, t1, w1;
    row_eval(tab, j, psi, &i0, &t0, &w0);
    row_eval(tab, j1, psi, &i1, &t1, &w1);
    *i = i0 + f * (i1 - i0);
    *torque = t0 + f * (t1 - t0);
    *w = w0 + f * (w1 - w0);
}
