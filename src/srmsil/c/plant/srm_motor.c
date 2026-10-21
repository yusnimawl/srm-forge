#include <math.h>

#include "srm_plant.h"

/* One table row at the flux grid coordinate s = psi / psi_step: linear in flux, extending the last two columns
   beyond the grid. Indices are int: the grids are far below 2^31 entries, and int conversions are single
   instructions on the Cortex-M7 where 64-bit ones are library calls. */
#ifndef SRM_TABLE_FLOAT
static void row_eval(const srm_sim_tables_t *tab, int row, double s, double *i, double *torque, double *w)
{
    const int n = (int)tab->n_psi;
    const srm_table_t *ci = tab->current + row * n, *ct = tab->torque + row * n;
    const srm_table_t *cw = tab->w_field ? tab->w_field + row * n : NULL;
    if (s >= (double)(n - 1)) {
        double d = s - (double)(n - 1);
        *i = ci[n - 1] + d * (ci[n - 1] - ci[n - 2]);
        *torque = ct[n - 1] + d * (ct[n - 1] - ct[n - 2]);
        *w = cw ? cw[n - 1] + 0.5 * d * tab->psi_step * (ci[n - 1] + *i) : 0.0;
        return;
    }
    int k = (int)s;
    double f = s - (double)k;
    *i = ci[k] + f * (ci[k + 1] - ci[k]);
    *torque = ct[k] + f * (ct[k + 1] - ct[k]);
    *w = cw ? cw[k] + f * (cw[k + 1] - cw[k]) : 0.0;
}
#endif

#ifdef SRM_TABLE_FLOAT
/* Float-table build (the real-time emulator and its PC model, srm_emu.c): the lookup runs in single precision, which
   matches the float tables and fits the Cortex-M7's 5 us step. */
static void row_eval_f(const srm_sim_tables_t *tab, int row, float s, float *i, float *torque, float *w)
{
    const int n = (int)tab->n_psi;
    const float *ci = tab->current + row * n, *ct = tab->torque + row * n;
    const float *cw = tab->w_field ? tab->w_field + row * n : NULL;
    if (s >= (float)(n - 1)) {
        float d = s - (float)(n - 1);
        *i = ci[n - 1] + d * (ci[n - 1] - ci[n - 2]);
        *torque = ct[n - 1] + d * (ct[n - 1] - ct[n - 2]);
        *w = cw ? cw[n - 1] + 0.5f * d * (float)tab->psi_step * (ci[n - 1] + *i) : 0.0f;
        return;
    }
    int k = (int)s;
    float f = s - (float)k;
    *i = ci[k] + f * (ci[k + 1] - ci[k]);
    *torque = ct[k] + f * (ct[k + 1] - ct[k]);
    *w = cw ? cw[k] + f * (cw[k + 1] - cw[k]) : 0.0f;
}

void srm_motor_lookup_f(const srm_sim_tables_t *tab, float u, float s, float *i, float *torque, float *w)
{
    const int n_theta = (int)tab->n_theta;
    if (!(u >= 0.0f)) u = 0.0f;
    int j = (int)u;
    if (j >= n_theta) j = n_theta - 1;
    float f = u - (float)j;
    int j1 = (j + 1 == n_theta) ? 0 : j + 1;
    float i0, t0, w0, i1, t1, w1;
    row_eval_f(tab, j, s, &i0, &t0, &w0);
    row_eval_f(tab, j1, s, &i1, &t1, &w1);
    *i = i0 + f * (i1 - i0);
    *torque = t0 + f * (t1 - t0);
    *w = w0 + f * (w1 - w0);
}

/* Zero flux gives zero current, torque and field energy without a lookup (the tables' zero-flux column). */
void srm_motor_eval(const srm_sim_tables_t *tab, double theta_phase, double psi, double *i, double *torque,
                    double *w)
{
    if (!(psi > 0.0) || !isfinite(psi)) {
        *i = *torque = *w = 0.0;
        return;
    }
    const double period = tab->theta_step * (double)tab->n_theta;
    double th = theta_phase - period * floor(theta_phase / period);
    if (!isfinite(th)) th = 0.0;
    float fi, ft, fw;
    srm_motor_lookup_f(tab, (float)th / (float)tab->theta_step, (float)psi / (float)tab->psi_step, &fi, &ft, &fw);
    *i = (double)fi;
    *torque = (double)ft;
    *w = (double)fw;
}

#else

void srm_motor_eval(const srm_sim_tables_t *tab, double theta_phase, double psi, double *i, double *torque,
                    double *w)
{
    const int n_theta = (int)tab->n_theta;
    double period = tab->theta_step * (double)n_theta;
    if (!(psi > 0.0)) psi = 0.0;
    if (!isfinite(psi)) psi = 0.0;
    double th = fmod(theta_phase, period);
    if (!isfinite(th)) th = 0.0;
    if (th < 0.0) th += period;
    double u = th / tab->theta_step;
    int j = (int)u;
    if (j >= n_theta) j = n_theta - 1;
    double f = u - (double)j;
    int j1 = (j + 1 == n_theta) ? 0 : j + 1;
    const double s = psi / tab->psi_step;
    double i0, t0, w0, i1, t1, w1;
    row_eval(tab, j, s, &i0, &t0, &w0);
    row_eval(tab, j1, s, &i1, &t1, &w1);
    *i = i0 + f * (i1 - i0);
    *torque = t0 + f * (t1 - t0);
    *w = w0 + f * (w1 - w0);
}

#endif
