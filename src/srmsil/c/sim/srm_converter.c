#include <math.h>

#include "srm_sim.h"

void srm_conv_init(srm_conv_t *c, const srm_sim_config_t *cfg)
{
    c->cfg = cfg;
    c->n_phases = cfg->n_phases;
    c->bus = cfg->bus_voltage;
    c->v_switch = cfg->v_switch;
    c->v_diode = cfg->v_diode;
    c->pwm_hz = cfg->pwm_hz * cfg->controller_clock;    /* the carrier runs on the controller's clock */
    c->rise_steps = (int64_t)llround((cfg->dead_time + cfg->turn_on_delay) / cfg->dt);
    c->fall_steps = (int64_t)llround(cfg->turn_off_delay / cfg->dt);
    for (int k = 0; k < SRM_SIM_MAX_PHASES; k++) {
        srm_phase_gates_t g = {0};
        c->ph[k] = g;
    }
}

void srm_conv_set_direct(srm_conv_t *c, int phase, int upper, int lower)
{
    srm_phase_gates_t *g = &c->ph[phase];
    g->mode = 0;
    g->u_cmd = upper != 0;
    g->l_cmd = lower != 0;
}

void srm_conv_set_pwm(srm_conv_t *c, int phase, double duty, int chop)
{
    srm_phase_gates_t *g = &c->ph[phase];
    g->mode = 1;
    g->duty = duty;
    g->chop = chop;
}

/* A commanded level reaches the switch after the rise or fall delay, provided it holds that long. */
static void follow(int cmd, int *eff, int64_t *cnt, int64_t rise, int64_t fall)
{
    if (cmd == *eff) {
        *cnt = 0;
        return;
    }
    if (*cnt >= (cmd ? rise : fall)) {
        *eff = cmd;
        *cnt = 0;
    } else {
        (*cnt)++;
    }
}

void srm_conv_step(srm_conv_t *c, double t)
{
    for (int k = 0; k < c->n_phases; k++) {
        srm_phase_gates_t *g = &c->ph[k];
        int u = g->u_cmd, l = g->l_cmd;
        if (g->mode == 1) {
            double ph = fmod(t * c->pwm_hz, 1.0);
            double carrier = ph < 0.5 ? 2.0 * ph : 2.0 * (1.0 - ph);
            u = g->duty >= 1.0 || (g->duty > 0.0 && carrier > 1.0 - g->duty);
            l = g->chop ? 1 : u;
        }
        follow(u, &g->u_eff, &g->u_cnt, c->rise_steps, c->fall_steps);
        follow(l, &g->l_eff, &g->l_cnt, c->rise_steps, c->fall_steps);
    }
}

double srm_conv_voltage(const srm_conv_t *c, int phase, double current)
{
    const srm_phase_gates_t *g = &c->ph[phase];
    return srm_ahb_voltage(c->cfg, g->u_eff, g->l_eff, current);
}
