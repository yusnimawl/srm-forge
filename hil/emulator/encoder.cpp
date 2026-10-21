// Emulated quadrature encoder: A/B/Z on Teensy 2/3/4 (GPIO9 bits 4, 5, 6).
//
// Each step computes the count boundaries crossed from the measured angle before the step to the one after it
// (outputs.cpp measured_turns, the SIL encoder model; enc_sched.c) and schedules their edges on GPT2 (24 MHz
// oscillator, compare 1, priority EMU_PRIO_ENCODER) at the interpolated times, shifted by two steps: the edges of step call k go out over [g0 + (k + 2) P, g0 + (k + 3) P), P =
// EMU_GPT_STEP ticks, where g0 is the GPT2 count at the first call after a start. The step timer runs on the same
// oscillator, so the schedule does not drift, and a step call always ends well before its edges are due. While RUN is
// low the plant holds and so does the encoder.
#include <Arduino.h>
#include <math.h>

#include "emu.h"
#include "enc_sched.h"

#ifdef EMU_ENCODER

#define EDGES_PER_STEP 8         // 4 * cpr * rev/s <= 400 000 /s gives at most 2 per 5 us step
#define QUEUE 32                  // power of two
#define EDGE_RATE_MAX 400000.0
#define NEAR 48                   // ticks, 2 us

struct Edge {
    uint32_t tick;
    uint8_t state;
};

static Edge queue[QUEUE];
static volatile uint32_t head, tail;     // head: step interrupt, tail: GPT2 interrupt
static volatile bool armed;
static uint32_t due;                     // tick of the programmed compare
static uint32_t cpr, calls, g0;
static double c_prev;                    // count position after the last step

static inline void put(uint8_t s)
{
    const uint32_t bits = (uint32_t)(s & 7u) << 4;
    GPIO9_DR_CLEAR = (7u << 4) & ~bits;
    GPIO9_DR_SET = bits;
}

// Compare match at `due`: puts every edge due by then, and programs the next one. GPT2 register reads are slow (the
// peripheral bus), so the counter is read only for an edge within NEAR ticks of the last compare; a later one is
// programmed directly, since this interrupt never runs that late (priority EMU_PRIO_ENCODER, below only the short
// pin interrupt and critical sections).
static void enc_isr()
{
    GPT2_SR = GPT_SR_OF1;
    if (!armed) {                   // the unprogrammed compare's match once per counter wrap
        asm volatile("dsb");
        return;
    }
    for (;;) {
        const uint32_t t = tail;
        if (t == head) {            // the compare stays enabled: its next match, a wrap later, finds nothing to do
            armed = false;
            break;
        }
        const Edge &e = queue[t & (QUEUE - 1)];
        const int32_t ahead = (int32_t)(e.tick - due);
        if (ahead > NEAR) {
            GPT2_OCR1 = e.tick;
            due = e.tick;
            break;
        }
        if (ahead > 0 && (int32_t)(e.tick - GPT2_CNT) > 0) {
            GPT2_OCR1 = e.tick;
            due = e.tick;
            if ((int32_t)(e.tick - GPT2_CNT) > 0) break;     // else it passed while the compare was set
        }
        put(e.state);
        tail = t + 1;
    }
    asm volatile("dsb");
}

void encoder_begin(void)
{
    pinMode(2, OUTPUT);
    pinMode(3, OUTPUT);
    pinMode(4, OUTPUT);
    put(0);
    CCM_CCGR0 |= CCM_CCGR0_GPT2_BUS(CCM_CCGR_ON) | CCM_CCGR0_GPT2_SERIAL(CCM_CCGR_ON);
    GPT2_CR = 0;
    GPT2_CR = GPT_CR_SWR;
    while (GPT2_CR & GPT_CR_SWR) {}
    GPT2_PR = 0;
    GPT2_CR = GPT_CR_CLKSRC(5) | GPT_CR_EN_24M | GPT_CR_FRR | GPT_CR_ENMOD;
    GPT2_CR |= GPT_CR_EN;
    GPT2_OCR1 = 0xFFFFFFFF;
    GPT2_IR = GPT_IR_OF1IE;
    attachInterruptVector(IRQ_GPT2, enc_isr);
    NVIC_SET_PRIORITY(IRQ_GPT2, EMU_PRIO_ENCODER);
    NVIC_ENABLE_IRQ(IRQ_GPT2);
}

const char *encoder_configure(const hil_emu_config_t *c)
{
    if (c->encoder_cpr < 1) return "config refused: encoder_cpr";
    // fixed speed: the edge rate is known now (dynamic runs are the host's check, srmsil.hil.config.check_encoder_rate)
    if (c->mode == 0 && 4.0 * c->encoder_cpr * fabs((double)c->speed) / (2.0 * M_PI) > EDGE_RATE_MAX)
        return "config refused: encoder edge rate 4 * cpr * rev/s exceeds 400000 /s";
    cpr = c->encoder_cpr;
    return NULL;
}

static inline uint8_t state_at(double c) { return enc_state((int64_t)floor(c), cpr); }

void encoder_start(double turns)
{
    NVIC_DISABLE_IRQ(IRQ_GPT2);
    armed = false;
    head = tail = 0;
    GPT2_OCR1 = GPT2_CNT - 1;       // next match a wrap away
    GPT2_SR = GPT_SR_OF1;
    NVIC_CLEAR_PENDING(IRQ_GPT2);
    NVIC_ENABLE_IRQ(IRQ_GPT2);
    c_prev = turns * cpr;
    calls = 0;
    put(state_at(c_prev));
}

// Base tick of this step call's edges.
static uint32_t next_base()
{
    if (calls == 0) g0 = GPT2_CNT;
    return g0 + (calls++ + 2) * EMU_GPT_STEP;
}

void encoder_update(double turns)
{
    const uint32_t base = next_base();
    const double c = turns * cpr;
    if (floor(c) == floor(c_prev)) {      // no edge in most steps
        c_prev = c;
        return;
    }
    double t[EDGES_PER_STEP];
    uint8_t s[EDGES_PER_STEP];
    const int n = enc_edges_c(c_prev, c, cpr, 0.0, (double)EMU_GPT_STEP, t, s, EDGES_PER_STEP);
    c_prev = c;
    if (n < 0 || head - tail + (uint32_t)n > QUEUE) {
        // faster than the rate check allows (or a full queue): jump to the count after the step
        put(state_at(c));
    } else {
        for (int j = 0; j < n; j++) {
            Edge &e = queue[(head + j) & (QUEUE - 1)];
            e.tick = base + (uint32_t)t[j];
            e.state = s[j];
        }
        head += n;
        // Unarmed, the interrupt cannot run (it only follows a programmed compare), so this does not race with it;
        // armed, it will find the new head. The first queued edge is at least a step ahead (next_base), so the
        // compare cannot be missed.
        if (!armed) {
            armed = true;
            due = queue[tail & (QUEUE - 1)].tick;
            GPT2_OCR1 = due;
        }
    }
}

void encoder_hold(void) { next_base(); }

#endif
