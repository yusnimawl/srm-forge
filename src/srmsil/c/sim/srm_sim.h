#ifndef SRM_SIM_H
#define SRM_SIM_H

#include <stddef.h>
#include <stdint.h>

#include "srm_plant.h"
#include "srm_sensors.h"

#define SRM_SIM_ABI 5

#if defined(_WIN32) && defined(SRM_SIM_BUILD)
#define SRM_SIM_API __declspec(dllexport)
#elif defined(SRM_SIM_BUILD)
#define SRM_SIM_API __attribute__((visibility("default")))
#else
#define SRM_SIM_API
#endif

typedef struct {
    int64_t n_samples;
    double *t, *theta, *omega, *torque, *encoder;           /* n */
    double *resolver_sin, *resolver_cos;                    /* n, raw counts, 0 without a resolver */
    float *i, *psi, *v, *adc_i, *adc_v;                     /* n_phases x n, phase-major; adc_v is 0 without voltage channels */
    uint8_t *gate_u, *gate_l;
} srm_sim_trace_t;

typedef struct {
    int64_t beyond_map_steps, window_steps;
    double energy_in, energy_mech, energy_copper, w_field_start, w_field_end;
    double torque_sum, torque_min, torque_max, copper_sum, power_in_sum, power_mech_sum;
    double i2_sum[SRM_SIM_MAX_PHASES];
    int32_t refused, refused_code;      /* 1-based index of the param step ctrl_param refused, and its code; 0 = none */
} srm_sim_summary_t;

SRM_SIM_API int srm_sim_abi(void);
SRM_SIM_API size_t srm_sim_sizeof_config(void);
SRM_SIM_API size_t srm_sim_sizeof_tables(void);
SRM_SIM_API size_t srm_sim_sizeof_trace(void);
SRM_SIM_API size_t srm_sim_sizeof_summary(void);
SRM_SIM_API int srm_sim_param(const char *name, float value);
/* 0 ok, -1 bad configuration, -2 gate command queue overflow, -3 a param step was refused (see the summary) */
SRM_SIM_API int srm_sim_run(const srm_sim_config_t *cfg, const srm_sim_tables_t *tab, srm_sim_trace_t *trace,
                            srm_sim_summary_t *summary);

/* Converter: gate commands, switch delays, PWM and the winding voltage. */
typedef struct {
    int mode;                   /* 0 direct, 1 pwm */
    int u_cmd, l_cmd;
    double duty;
    int chop;                   /* 0 hard, 1 soft */
    int u_eff, l_eff;
    int64_t u_cnt, l_cnt;
} srm_phase_gates_t;

typedef struct {
    const srm_sim_config_t *cfg;
    int n_phases;
    double bus, v_switch, v_diode, pwm_hz;
    int64_t rise_steps, fall_steps;
    srm_phase_gates_t ph[SRM_SIM_MAX_PHASES];
} srm_conv_t;

void srm_conv_init(srm_conv_t *c, const srm_sim_config_t *cfg);
void srm_conv_set_direct(srm_conv_t *c, int phase, int upper, int lower);
void srm_conv_set_pwm(srm_conv_t *c, int phase, double duty, int chop);
/* Advance the switch delays by one step at time t and update the effective gates. */
void srm_conv_step(srm_conv_t *c, double t);
double srm_conv_voltage(const srm_conv_t *c, int phase, double current);

#endif
