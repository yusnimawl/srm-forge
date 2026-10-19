/* Torque sharing function controller. Each phase has a share s of the torque command: a cubic rise
 * s(x) = 3x^2 - 2x^3 over `overlap` electrical degrees from `theta_on`, 1 until `theta_on` + stroke, and the
 * mirror fall over the next `overlap` degrees (stroke = 360 / phases). Neighbouring shares sum to 1, so the
 * commanded torque is handed from one phase to the next. Phase k gets i_ref = i*(theta_k, s * T_cmd) from the
 * torque table and a PI current loop; a phase with no share is off. Intended pwm_hz: 20 kHz. */
#include "srm_ctrl.h"
#include "srm_motor_tables.h"
#include "srm_ref.h"

static const srm_hal_t *hal;
static float theta_on = 15.0f;   /* electrical degrees from unaligned; negative = advanced */
static float overlap = 30.0f;    /* electrical degrees, at most one stroke */
static float kp = 0.0f;          /* V/A; 0 = derived from f_bw */
static float ki = 0.0f;          /* V/(A*s); 0 = derived from f_bw */
static float f_bw = 0.0f;        /* Hz; 0 = pwm_hz / 20 */
static float integ[SRM_N_PHASES];   /* V */
static float dt;

/* Searched before the shared table, so this theta_on (default 15) replaces the shared window start. */
static const srm_ref_param_t own[] = {
    {"theta_on", &theta_on},
    {"overlap", &overlap},
    {"kp", &kp},
    {"ki", &ki},
    {"f_bw", &f_bw},
};

int ctrl_param(const char *name, float value)
{
    return srm_ref_param(own, (int)(sizeof own / sizeof own[0]), name, value);
}

void ctrl_init(const srm_hal_t *h)
{
    hal = h;
    srm_ref_init(h);
    dt = srm_ref_ok() ? 1.0f / h->isr_hz : 0.0f;
    srm_ref_pi_gains(h, f_bw, &kp, &ki);
    for (int k = 0; k < SRM_N_PHASES; k++) integ[k] = 0.0f;
}

void ctrl_command(srm_cmd_mode_t mode, float value) { srm_ref_command(mode, value); }

void ctrl_slow(void) { srm_ref_slow(); }

static float smooth(float x) { return x * x * (3.0f - 2.0f * x); }

/* Share of a phase at electrical angle el_deg. */
static float share(float el_deg)
{
    float stroke = 360.0f / (float)SRM_N_PHASES;
    float ov = overlap < 0.0f ? 0.0f : (overlap > stroke ? stroke : overlap);
    float x = el_deg - theta_on;   /* degrees since turn-on, wrapped into [0, 360) */
    while (x < 0.0f) x += 360.0f;
    while (x >= 360.0f) x -= 360.0f;
    if (x < ov) return smooth(x / ov);
    if (x < stroke) return 1.0f;
    if (x < stroke + ov) return 1.0f - smooth((x - stroke) / ov);
    return 0.0f;
}

void ctrl_isr(void)
{
    if (!srm_ref_ok()) {
        for (uint8_t k = 0; k < hal->n_phases; k++) hal->set_switches(k, false, false);
        return;
    }
    float theta = srm_ref_angle(hal);
    float t_cmd = srm_ref_torque_cmd();
    float vbus = hal->vbus_volts();
    if (!(vbus > 1.0f)) vbus = 1.0f;
    for (uint8_t k = 0; k < hal->n_phases && k < SRM_N_PHASES; k++) {
        float th = srm_ref_phase_angle(theta, k);
        float s = share(srm_ref_el_deg(th));
        float i_ref = s > 0.0f ? srm_i_of_t(th, s * t_cmd) : 0.0f;
        if (i_ref <= 0.0f) {
            integ[k] = 0.0f;
            hal->set_switches(k, false, false);
            continue;
        }
        float duty = srm_ref_pi_duty(&integ[k], i_ref - srm_ref_current(hal, k), kp, ki, dt, vbus);
        hal->set_pwm(k, duty, SRM_CHOP_SOFT);
    }
}
