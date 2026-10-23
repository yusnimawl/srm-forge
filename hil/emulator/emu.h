/* Teensy 4.1 real-time SRM emulator: shared state and the interfaces between its parts.
 *
 * step.cpp    200 kHz step interrupt: gate edges -> averaged winding voltages -> plant step -> outputs, health
 * gates.cpp   gate inputs (pins 14..21, fast GPIO6) on the combined GPIO6-9 interrupt, cycle-counter stamps
 * link.cpp    USB framing, config and table upload, live statistics, capture ring and its transfer
 * safety.cpp  RUN input (pin 7) and READY output (pin 8)
 * outputs.cpp the output stage of the build's modes, and the output pins on the combined GPIO interrupt
 * ad7606_slave.cpp, ad2s1210_slave.cpp, dac.cpp, encoder.cpp  the emulated sensor chips (one per mode)
 * ga_selfcheck.c  self-check of the compiled gate averager, run by every START (portable C)
 *
 * Interrupt priorities (lower is more urgent): gates and CONVST, then the encoder timer, then the step timer; USB
 * stays at the core's default 128. Time is the ARM cycle counter (F_CPU_ACTUAL, 1008 MHz from platformio.ini; every
 * cycle constant is derived from it), extended to 64 bits by the step interrupt. */
#ifndef EMU_H
#define EMU_H

#include <stdint.h>

extern "C" {
#include "edge_ring.h"
#include "ga_selfcheck.h"
#include "hil_proto.h"
#include "srm_gate_avg.h"
#include "srm_plant.h"
}

#define EMU_MAX_THETA 180
#define EMU_MAX_PSI 192
#define EMU_STEP_HZ 200000
#define EMU_DT 5e-6
#define EMU_MAX_PHASES 4
#define EMU_PRIO_GATES 0
#define EMU_PRIO_ENCODER 16
#define EMU_PRIO_STEP 32
#define EMU_OVERLOAD_STEPS 20          /* a step finishing this many steps late stops the loop */
#define EMU_STATS_STEPS 10000          /* one live-statistics window: 50 ms, 20 Hz */
#define EMU_SELFTEST_HZ 20000
#define EMU_SELFTEST_OFFSET 1000       /* cycles from the start of the first pattern window to its first rise */
#define EMU_TEMP_MAX_C 85.0f           /* die temperature that stops a run */
#define EMU_CAPTURE_RING 8192          /* samples, the largest power of two whose ring fits in DMAMEM */
#define EMU_GPT_HZ 24000000            /* output timers (GPT2): the peripheral clock, the 24 MHz oscillator as for the step timer's PIT */
#define EMU_GPT_STEP 120               /* GPT ticks per step */

/* Output modes of the build (hil_hello.h codes the same macros; no macro means ad7606 and encoder). */
#ifdef HIL_CURRENT_SENSE_INTERNAL
#define EMU_DAC 1
#else
#define EMU_AD7606 1
#endif
#if defined(HIL_POSITION_ENCODER) || !defined(HIL_POSITION_AD2S1210)
#define EMU_ENCODER 1
#endif
#ifdef HIL_POSITION_AD2S1210
#define EMU_RDC 1
#endif

/* x rounded half away from zero and saturated to int16 without branches (float to int saturates; NaN gives 0). */
static inline int16_t emu_sat16(float x)
{
    int32_t n = (int32_t)(x + __builtin_copysignf(0.5f, x));
    asm("ssat %0, #16, %1" : "=r"(n) : "r"(n));
    return (int16_t)n;
}

extern srm_table_t g_current[EMU_MAX_THETA * EMU_MAX_PSI], g_torque[EMU_MAX_THETA * EMU_MAX_PSI];
extern emu_edge_ring_t g_edges;
extern volatile bool g_selftest;       /* the software pattern replaces the gate inputs and RUN */

/* step.cpp; called from loop() context. Each returns NULL on success or an error text. */
const char *emu_configure(const hil_emu_config_t *c);
const char *emu_table_chunk(const hil_table_chunk_t *c);
const char *emu_start(void);
void emu_stop(void);
bool emu_running(void);
bool emu_take_overload(void);                      /* the step loop stopped itself, once */
void emu_set_selftest(float duty);
void emu_set_selftest_phases(unsigned mask);       /* phases of the pattern, bit k = phase k; from the next start of it */
bool emu_live_take(hil_live_emu_t *out);           /* the latest finished statistics window, once */
hil_capture_hdr_t emu_capture_header(uint32_t n_steps);
uint32_t emu_capture_default_steps(void);
uint32_t emu_overruns(void);
float emu_step_max_us(void);
void emu_output_fault(void);                      /* step interrupt: an output fault, counted as an overrun */
/* Cycles since start: gate_avg[0] max, [1] mean, [2] mean of the whole step; plant[0] max, [1] mean. */
void emu_profile(uint32_t gate_avg[3], uint32_t plant[3]);

/* link.cpp */
void link_begin(void);
void link_poll(void);
bool cap_wants_sample(void);                      /* step interrupt: is a capture recording */
void cap_push(const hil_sample_t *s);             /* step interrupt */
uint32_t cap_dropped(void);                       /* samples a full ring refused plus frames cut by a short USB write, since the last start */
void cap_reset_dropped(void);
void cap_abort(void);                             /* stop during a capture */

/* gates.cpp */
void gates_begin(void);

/* safety.cpp */
void safety_begin(void);
bool safety_run(void);                             /* RUN high, or the self-test pattern active */
void safety_ready(bool on);

/* outputs.cpp: the output stage of a step (sensed values, encoder schedule, resolver registers) from the plant state
 * after the step and the winding voltages averaged over it. emu_outputs_zero presents the zero-current state (RUN
 * low, stop). Each step interrupt calls exactly one of the two. */
void outputs_begin(void);
const char *outputs_configure(const hil_emu_config_t *c);
void outputs_start(const srm_plant_t *p);
void emu_outputs_update(const srm_plant_t *p, const srm_real_t *v);
void emu_outputs_zero(void);
void outputs_pins_isr(uint32_t t, uint32_t isr6);  /* combined GPIO interrupt entered at cycle t, GPIO6_ISR read there: input pins */
void outputs_trigger_reset(void);                 /* with the GPIO interrupt disabled */
void outputs_trigger_stamp(uint32_t t);           /* a sample trigger at cycle t, from its interrupt (priority 0) */
float outputs_trigger_hz(void);                   /* step interrupt: triggers per s since the last call */

/* The chips, one file each, compiled in their modes only. */
void ad7606_begin(void);
const char *ad7606_configure(const hil_emu_config_t *c);
void ad7606_start(void);
void ad7606_update(const srm_plant_t *p, const srm_real_t *v);
void ad7606_zero(void);
void rdc_begin(void);
const char *rdc_configure(const hil_emu_config_t *c);
void rdc_start(double turns, float omega);       /* turns: measured mechanical angle (outputs.cpp) */
void rdc_update(double turns, float omega);
void rdc_sample(void);                            /* SAMPLE falling edge */
void rdc_select(void);                            /* A0 or A1 changed */
void dac_begin(void);
const char *dac_configure(const hil_emu_config_t *c);
void dac_update(const srm_plant_t *p);
void dac_zero(void);
void dac_run_low(void);                           /* RUN falling edge: release the shared SPI wires */
void encoder_begin(void);
const char *encoder_configure(const hil_emu_config_t *c);
void encoder_start(double turns);
void encoder_update(double turns);
void encoder_hold(void);

#endif
