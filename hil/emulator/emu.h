/* Teensy 4.1 real-time SRM emulator: shared state and the interfaces between its parts.
 *
 * step.cpp    200 kHz step interrupt: gate edges -> averaged winding voltages -> plant step -> outputs, health
 * gates.cpp   gate inputs (pins 14..21, fast GPIO6) on the combined GPIO6-9 interrupt, cycle-counter stamps
 * link.cpp    USB framing, config and table upload, live statistics, capture ring and its transfer
 * safety.cpp  RUN input (pin 7) and READY output (pin 8)
 *
 * Interrupt priorities (lower is more urgent): gates, then the encoder timer, then the step timer; USB stays at the
 * core's default 128. Time is the ARM cycle counter (F_CPU_ACTUAL), extended to 64 bits by the step interrupt. */
#ifndef EMU_H
#define EMU_H

#include <stdint.h>

extern "C" {
#include "edge_ring.h"
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
#define EMU_CAPTURE_RING 8192          /* samples, the largest power of two whose ring fits in DMAMEM */

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
/* Cycles since start: gate_avg[0] max, [1] mean, [2] mean of the whole step; plant[0] max, [1] mean. */
void emu_profile(uint32_t gate_avg[3], uint32_t plant[3]);

/* link.cpp */
void link_begin(void);
void link_poll(void);
bool cap_wants_sample(void);                      /* step interrupt: is a capture recording */
void cap_push(const hil_sample_t *s);             /* step interrupt */
uint32_t cap_dropped(void);
void cap_abort(void);                             /* stop during a capture */

/* gates.cpp */
void gates_begin(void);

/* safety.cpp */
void safety_begin(void);
bool safety_run(void);                             /* RUN high, or the self-test pattern active */
void safety_ready(bool on);

/* Output stage of a step: sensed values, encoder schedule, resolver registers. emu_outputs_zero presents the
 * zero-current state while RUN is low. */
void emu_outputs_update(const srm_plant_t *p);
void emu_outputs_zero(void);

#endif
