#ifndef SRM_PLANT_H
#define SRM_PLANT_H

#include <stddef.h>
#include <stdint.h>

#define SRM_SIM_MAX_PHASES 8

/* Element type of the flux-grid tables, and the real type of the plant state and arithmetic (fluxes, currents,
   torques, speed, the gate averager). SRM_TABLE_FLOAT selects float for both: the real-time emulator, whose
   Cortex-M7 has a fast single-precision FPU, and its PC model srm_emu.c, which uses the same configuration. The SIL
   builds use double. The rotor angle and the time stay double in both builds: an unwrapped float angle would lose
   resolution as it grows. SRM_REAL(x) writes a literal of the real type. */
#ifdef SRM_TABLE_FLOAT
typedef float srm_table_t;
typedef float srm_real_t;
#define SRM_REAL(x) x##f
#else
typedef double srm_table_t;
typedef double srm_real_t;
#define SRM_REAL(x) x
#endif

/* A controller parameter set at a simulation time: applied through ctrl_param just before the first ISR at or after t. */
typedef struct {
    double t;
    float value;
    char name[24];
} srm_param_step_t;

/* The structs are mirrored by ctypes: 8-byte members first, then 4-byte members. */
typedef struct {
    double resistance, bus_voltage, dt, speed, theta0;
    double inertia, friction, load, load_step, load_step_time;
    double pwm_hz, isr_hz, compute_delay, command_value;
    double v_switch, v_diode, dead_time, turn_on_delay, turn_off_delay;
    double adc_amps_per_count;
    double encoder_offset, encoder_ecc_amp;
    double resolver_gain_mismatch, resolver_phase_error;
    double adc_offset_error, adc_gain_error, adc_noise, adc_rc_tau;
    double sensor_delay;        /* s, transport delay of the sensed currents and voltages */
    double volt_full_scale;     /* V at the top code of the bipolar voltage channels, 0 = no voltage channels */
    double volt_rc_tau;         /* s, first-order filter on the sensed voltages, 0 = none */
    int64_t n_steps, trace_stride;
    const srm_param_step_t *param_steps;    /* n_param_steps entries in time order */
    int32_t n_phases, n_rotor_poles;
    int32_t mode;               /* 0 fixed speed, 1 dynamic */
    int32_t command_mode;       /* 0 torque, 1 speed */
    uint32_t encoder_cpr;
    int32_t adc_bits, adc_offset_counts;
    uint32_t seed;
    int32_t encoder_ecc_harmonic, resolver, resolver_pole_pairs, resolver_bits;
    int32_t n_param_steps;
} srm_sim_config_t;

typedef struct {
    double theta_step, psi_step, psi_max, i_max;
    int64_t n_theta, n_psi;
    const srm_table_t *current, *torque, *w_field;      /* w_field may be NULL */
} srm_sim_tables_t;

/* Rotor angle and speed, total torque, and flux, current, torque and field energy of every phase. */
typedef struct {
    double theta;
    srm_real_t omega, ttot;
    srm_real_t psi[SRM_SIM_MAX_PHASES], cur[SRM_SIM_MAX_PHASES], trq[SRM_SIM_MAX_PHASES], wf[SRM_SIM_MAX_PHASES];
    /* Constants set by srm_plant_init: config values in the real type, and the lookup constants of the float-table
       build (phase shift, table period and its inverse, inverse grid steps). */
    srm_real_t k_dt, k_r, k_inertia, k_friction, k_load, k_load_step;
    double k_eps, k_period, k_inv_period;
    float k_inv_theta, k_inv_psi;
} srm_plant_t;

/* Motor: bilinear lookup of i, T and field energy W at a phase angle (wrapped here) and flux. W is 0 without a
   w_field table. */
void srm_motor_eval(const srm_sim_tables_t *tab, double theta_phase, double psi, double *i, double *torque,
                    double *w);
#ifdef SRM_TABLE_FLOAT
/* Float-table build: i, T and W at the table coordinates u = phase angle / theta_step in [0, n_theta] and
   s = psi / psi_step >= 0. */
void srm_motor_lookup_f(const srm_sim_tables_t *tab, float u, float s, float *i, float *torque, float *w);
#endif
/* i, T and W of every phase at rotor angle theta and fluxes psi; returns the total torque. */
srm_real_t srm_plant_eval(const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta, const srm_real_t *psi,
                          srm_real_t *i, srm_real_t *trq, srm_real_t *w);
/* Rotor at theta0 and speed with zero flux. */
void srm_plant_init(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t);
/* One Heun step of length dt with the winding voltages v held over the step; t_now is the time and n the step
   index (fixed-speed mode places the rotor from n). */
void srm_plant_step(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t, const srm_real_t *v,
                    double t_now, int64_t n);
/* Asymmetric half-bridge winding voltage for the effective switch states and the winding current. */
double srm_ahb_voltage(const srm_sim_config_t *c, int upper, int lower, double current);

#endif
