#include "srm_ref.h"

#include <math.h>
#include <string.h>

#include "srm_motor_tables.h"

#define PI_F 3.14159265f
#define TWO_PI_F 6.28318531f

static const srm_hal_t *hal_;

/* Shared parameters. */
static float theta_on = 0.0f;                 /* electrical degrees from unaligned */
static float theta_off = 150.0f;
static float speed_kp = 0.05f;                /* N*m / (rad/s) */
static float speed_ki = 0.5f;                 /* N*m / rad */
static float speed_filter_hz = 50.0f;
static float torque_limit = SRM_T_MAX_NM;     /* N*m */
static float resolver_pole_pairs = 1.0f;

static const srm_ref_param_t shared[] = {
    {"theta_on", &theta_on},
    {"theta_off", &theta_off},
    {"speed_kp", &speed_kp},
    {"speed_ki", &speed_ki},
    {"speed_filter_hz", &speed_filter_hz},
    {"torque_limit", &torque_limit},
    {"resolver_pole_pairs", &resolver_pole_pairs},
};

/* Command and speed-loop state. */
static srm_cmd_mode_t cmd_mode = SRM_CMD_TORQUE;
static float cmd_value = 0.0f;
static float torque_cmd = 0.0f;
static float speed_est = 0.0f;
static float integ = 0.0f;
static float last_theta = 0.0f;
static uint32_t last_us = 0;
static bool primed = false;

static int lookup(const srm_ref_param_t *t, int n, const char *name, float value)
{
    for (int i = 0; i < n; i++) {
        if (strcmp(t[i].name, name) == 0) {
            *t[i].value = value;
            return 0;
        }
    }
    return -1;
}

int srm_ref_param(const srm_ref_param_t *own, int n_own, const char *name, float value)
{
    if (lookup(own, n_own, name, value) == 0) return 0;
    return lookup(shared, (int)(sizeof shared / sizeof shared[0]), name, value);
}

static float clampf(float x, float lo, float hi)
{
    return x < lo ? lo : (x > hi ? hi : x);
}

void srm_ref_init(const srm_hal_t *hal)
{
    hal_ = hal;
    cmd_mode = SRM_CMD_TORQUE;
    cmd_value = 0.0f;
    torque_cmd = 0.0f;
    speed_est = 0.0f;
    integ = 0.0f;
    primed = false;
}

void srm_ref_command(srm_cmd_mode_t mode, float value)
{
    cmd_mode = mode;
    cmd_value = value;
    if (mode == SRM_CMD_TORQUE) torque_cmd = clampf(value, 0.0f, torque_limit);
}

float srm_ref_angle(const srm_hal_t *hal)
{
    if (hal->encoder_cpr > 0) {
        return TWO_PI_F * (float)hal->encoder_count() / (float)hal->encoder_cpr;
    }
    int16_t s, c;
    hal->resolver_sincos(&s, &c);
    float a = atan2f((float)s, (float)c);
    if (a < 0.0f) a += TWO_PI_F;
    return a / resolver_pole_pairs;
}

float srm_ref_phase_angle(float theta, uint8_t k)
{
    float p = fmodf(theta - (float)k * SRM_STROKE_RAD, SRM_POLE_PITCH_RAD);
    if (p < 0.0f) p += SRM_POLE_PITCH_RAD;
    if (p >= SRM_POLE_PITCH_RAD) p = 0.0f;
    return p;
}

float srm_ref_el_deg(float theta_phase)
{
    float e = fmodf(theta_phase * (float)SRM_N_ROTOR_POLES * 180.0f / PI_F + 180.0f, 360.0f);
    return e < 0.0f ? e + 360.0f : e;
}

bool srm_ref_in_window(float theta_phase)
{
    float e = srm_ref_el_deg(theta_phase);
    return e >= theta_on && e < theta_off;
}

float srm_ref_current(const srm_hal_t *hal, uint8_t k)
{
    return ((float)hal->adc_read(k) - (float)hal->adc_offset_counts) * hal->adc_amps_per_count;
}

float srm_ref_speed(void) { return speed_est; }

float srm_ref_torque_cmd(void) { return torque_cmd; }

float srm_ref_i_ref(void)
{
    /* The centre of the window is far from both ends, where i*(theta, T) is not reliable. */
    float centre_deg = 0.5f * (theta_on + theta_off);
    float theta_c = (centre_deg - 180.0f) * PI_F / 180.0f / (float)SRM_N_ROTOR_POLES;
    return srm_i_of_t(theta_c, torque_cmd);
}

void srm_ref_slow(void)
{
    float theta = srm_ref_angle(hal_);
    uint32_t now = hal_->micros();
    if (!primed) {
        last_theta = theta;
        last_us = now;
        primed = true;
        return;
    }
    float dt = (float)(now - last_us) * 1e-6f;
    if (dt <= 0.0f) return;
    float d = theta - last_theta;
    if (d > PI_F) d -= TWO_PI_F;
    if (d < -PI_F) d += TWO_PI_F;
    last_theta = theta;
    last_us = now;

    /* First-order low-pass on the raw speed from angle differences. */
    float alpha = 1.0f - expf(-TWO_PI_F * speed_filter_hz * dt);
    speed_est += alpha * (d / dt - speed_est);

    if (cmd_mode == SRM_CMD_SPEED) {
        float err = cmd_value - speed_est;
        /* The integral term alone is clamped to the torque range, which also bounds the windup. */
        integ = clampf(integ + speed_ki * err * dt, 0.0f, torque_limit);
        torque_cmd = clampf(speed_kp * err + integ, 0.0f, torque_limit);
    }
}
