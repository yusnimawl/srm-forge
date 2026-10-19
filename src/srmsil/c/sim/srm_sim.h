#ifndef SRM_SIM_H
#define SRM_SIM_H

#include <stddef.h>
#include <stdint.h>

#define SRM_SIM_ABI 1
#define SRM_SIM_MAX_PHASES 8

#if defined(_WIN32) && defined(SRM_SIM_BUILD)
#define SRM_SIM_API __declspec(dllexport)
#elif defined(SRM_SIM_BUILD)
#define SRM_SIM_API __attribute__((visibility("default")))
#else
#define SRM_SIM_API
#endif

/* The structs are mirrored by ctypes: 8-byte members first, then 4-byte members. */
typedef struct {
    double resistance, bus_voltage, dt, speed, theta0;
    double inertia, friction, load, load_step, load_step_time;
    double pwm_hz, isr_hz, compute_delay, command_value;
    double v_switch, v_diode, dead_time, turn_on_delay, turn_off_delay;
    double adc_amps_per_count;
    int64_t n_steps, trace_stride;
    int32_t n_phases, n_rotor_poles;
    int32_t mode;               /* 0 fixed speed, 1 dynamic */
    int32_t command_mode;       /* 0 torque, 1 speed */
    uint32_t encoder_cpr;
    int32_t adc_bits, adc_offset_counts;
    uint32_t seed;
} srm_sim_config_t;

typedef struct {
    double theta_step, psi_step, psi_max, i_max;
    int64_t n_theta, n_psi;
    const double *current, *torque, *w_field;
} srm_sim_tables_t;

typedef struct {
    int64_t n_samples;
    double *t, *theta, *omega, *torque, *encoder;           /* n */
    float *i, *psi, *v, *adc_i;                             /* n_phases x n, phase-major */
    uint8_t *gate_u, *gate_l;
} srm_sim_trace_t;

typedef struct {
    int64_t beyond_map_steps, window_steps;
    double energy_in, energy_mech, energy_copper, w_field_start, w_field_end;
    double torque_sum, torque_min, torque_max, copper_sum, power_in_sum, power_mech_sum;
    double i2_sum[SRM_SIM_MAX_PHASES];
} srm_sim_summary_t;

SRM_SIM_API int srm_sim_abi(void);
SRM_SIM_API size_t srm_sim_sizeof_config(void);
SRM_SIM_API size_t srm_sim_sizeof_tables(void);
SRM_SIM_API size_t srm_sim_sizeof_trace(void);
SRM_SIM_API size_t srm_sim_sizeof_summary(void);
SRM_SIM_API int srm_sim_param(const char *name, float value);
/* 0 ok, -1 bad configuration, -2 gate command queue overflow */
SRM_SIM_API int srm_sim_run(const srm_sim_config_t *cfg, const srm_sim_tables_t *tab, srm_sim_trace_t *trace,
                            srm_sim_summary_t *summary);

/* Motor: bilinear lookup of i, T and field energy W at a phase angle (wrapped here) and flux. */
void srm_motor_eval(const srm_sim_tables_t *tab, double theta_phase, double psi, double *i, double *torque,
                    double *w);

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
