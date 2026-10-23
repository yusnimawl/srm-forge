// Output stage: dispatches to the chips of the build's modes (emu.h EMU_*), and handles their input pins on the
// combined GPIO6-9 interrupt (priority 0, owned by gates.cpp): CONVST (pin 5, GPIO9), SAMPLE (pin 9, GPIO7), A0/A1
// (pins 22/23, GPIO6) and, in DAC builds, the RUN falling edge (pin 7, GPIO7), which releases the shared SPI wires.
#include <Arduino.h>

#include <math.h>

#include "emu.h"

#define PIN_RUN 7
#define PIN_CONVST 5
#define PIN_SAMPLE 9
#define PIN_RDC_A0 22
#define PIN_RDC_A1 23

#define SIN_TAB 1024

// The controller's sample triggers, one per controller ISR: CONVST in AD7606 builds, else SAMPLE in AD2S1210 builds,
// else none. The pins interrupt stamps them into trig[trig_sel]; outputs_trigger_hz (step interrupt, less urgent, so
// it never preempts a stamp) switches trig_sel and then reads the other buffer, which no stamp writes any more.
struct Trig {
    uint32_t n, first, last;      // count, first and last cycle stamp
};
static volatile Trig trig[2];
static volatile uint8_t trig_sel;

static inline void trig_stamp(uint32_t t)
{
    volatile Trig &b = trig[trig_sel];
    if (b.n++ == 0) b.first = t;
    b.last = t;
}

void outputs_trigger_reset(void)
{
    trig[0].n = trig[1].n = 0;
    trig_sel = 0;
}

// last - first is exact in 32 bits while the window is shorter than the cycle-counter wrap (4.26 s at 1008 MHz).
float outputs_trigger_hz(void)
{
    const uint8_t s = trig_sel;
    trig_sel = s ^ 1;             // the other buffer was emptied when it was last read
    volatile Trig &b = trig[s];
    const uint32_t n = b.n, span = b.last - b.first;
    b.n = 0;
    return n >= 2 && span ? (float)((double)(n - 1) * (double)F_CPU_ACTUAL / (double)span) : NAN;
}

static uint32_t bits6, bits7, bits9;     // the enabled pins of each port
static float sin_tab[SIN_TAB + 1];       // sin over one turn
static double off_turns, ecc_turns;      // encoder offset and eccentricity amplitude, in turns
static double ecc_harm;

// Measured mechanical angle of the SIL sensor model in turns, (theta + offset + ecc sin(h theta)) / (2 pi), unwrapped.
// The sine comes from a 1024-point table with linear interpolation: below 5e-6 of the amplitude, so 1e-8 rad at a
// 2 mrad eccentricity (the double sin() would cost about 400 cycles a step).
static double measured_turns(double theta)
{
    const double t = theta * (1.0 / (2.0 * M_PI));
    double m = t + off_turns;
    if (ecc_turns != 0.0) {
        double u = ecc_harm * t;
        u -= floor(u);
        const float f = (float)u * SIN_TAB;
        const int i = f < (float)SIN_TAB ? (int)f : SIN_TAB - 1;
        m += ecc_turns * (double)(sin_tab[i] + (f - (float)i) * (sin_tab[i + 1] - sin_tab[i]));
    }
    return m;
}

#define EDGE_RISING 2u        // GPIO ICR field values; EDGE_BOTH uses EDGE_SEL instead
#define EDGE_FALLING 3u
#define EDGE_BOTH 4u

// The GPIO block latches the selected edge in hardware, so a pulse shorter than the interrupt latency still counts;
// only A0/A1, whose level is the information, use both edges.
static void pin_irq(uint8_t pin, IMXRT_GPIO_t &g, uint32_t bit, uint32_t edge, uint32_t &bits)
{
    const uint32_t mask = 1u << bit;
    pinMode(pin, INPUT_PULLDOWN);
    g.IMR &= ~mask;
    if (edge == EDGE_BOTH) {
        g.EDGE_SEL |= mask;
    } else {
        g.EDGE_SEL &= ~mask;
        volatile uint32_t &icr = bit < 16 ? g.ICR1 : g.ICR2;
        const uint32_t sh = 2 * (bit & 15);
        icr = (icr & ~(3u << sh)) | edge << sh;
    }
    g.ISR = mask;
    g.IMR |= mask;
    bits |= mask;
}

void outputs_begin(void)
{
    for (int j = 0; j <= SIN_TAB; j++) sin_tab[j] = (float)sin(2.0 * M_PI * j / SIN_TAB);
#ifdef EMU_AD7606
    ad7606_begin();
    pin_irq(PIN_CONVST, IMXRT_GPIO9, CORE_PIN5_BIT, EDGE_RISING, bits9);
#endif
#ifdef EMU_DAC
    dac_begin();
    pin_irq(PIN_RUN, IMXRT_GPIO7, CORE_PIN7_BIT, EDGE_FALLING, bits7);
#endif
#ifdef EMU_RDC
    rdc_begin();
    pin_irq(PIN_SAMPLE, IMXRT_GPIO7, CORE_PIN9_BIT, EDGE_FALLING, bits7);
    pin_irq(PIN_RDC_A0, IMXRT_GPIO6, CORE_PIN22_BIT, EDGE_BOTH, bits6);
    pin_irq(PIN_RDC_A1, IMXRT_GPIO6, CORE_PIN23_BIT, EDGE_BOTH, bits6);
#endif
#ifdef EMU_ENCODER
    encoder_begin();
#endif
}

// Each GPIO register read costs tens of cycles on this path, so a port without enabled pins is not read.
void outputs_pins_isr(uint32_t t, uint32_t isr6)
{
    const uint32_t f6 = isr6 & bits6, f7 = bits7 ? GPIO7_ISR & bits7 : 0, f9 = bits9 ? GPIO9_ISR & bits9 : 0;
    if (f6) GPIO6_ISR = f6;
    if (f7) GPIO7_ISR = f7;
    if (f9) GPIO9_ISR = f9;
#ifdef EMU_DAC
    if (f7 & CORE_PIN7_BITMASK) dac_run_low();
#endif
#ifdef EMU_AD7606
    if (f9 & CORE_PIN5_BITMASK) {
        trig_stamp(t);
        ad7606_convst();
    }
#endif
#ifdef EMU_RDC
    if (f7 & CORE_PIN9_BITMASK) {
#ifndef EMU_AD7606
        trig_stamp(t);
#endif
        rdc_sample();
    }
    if (f6) rdc_select();
#endif
    (void)t;
}

const char *outputs_configure(const hil_emu_config_t *c)
{
    if (!isfinite(c->encoder_offset) || !isfinite(c->encoder_ecc_amp) ||
        (c->encoder_ecc_amp != 0.0f && c->encoder_ecc_harmonic < 1))
        return "config refused: encoder offset or eccentricity";
    off_turns = (double)c->encoder_offset / (2.0 * M_PI);
    ecc_turns = (double)c->encoder_ecc_amp / (2.0 * M_PI);
    ecc_harm = c->encoder_ecc_harmonic;
    const char *err = NULL;
#ifdef EMU_AD7606
    if (!err) err = ad7606_configure(c);
#endif
#ifdef EMU_DAC
    if (!err) err = dac_configure(c);
#endif
#ifdef EMU_RDC
    if (!err) err = rdc_configure(c);
#endif
#ifdef EMU_ENCODER
    if (!err) err = encoder_configure(c);
#endif
    (void)c;
    return err;
}

void outputs_start(const srm_plant_t *p)
{
    const double turns = measured_turns(p->theta);
    (void)turns;
#ifdef EMU_AD7606
    ad7606_start();
#endif
#ifdef EMU_RDC
    rdc_start(turns, p->omega);
#endif
#ifdef EMU_ENCODER
    encoder_start(turns);
#endif
    (void)p;
}

void emu_outputs_update(const srm_plant_t *p, const srm_real_t *v)
{
    const double turns = measured_turns(p->theta);
    (void)turns;
#ifdef EMU_AD7606
    ad7606_update(p, v);
#endif
#ifdef EMU_DAC
    dac_update(p);
#endif
#ifdef EMU_RDC
    rdc_update(turns, p->omega);
#endif
#ifdef EMU_ENCODER
    encoder_update(turns);
#endif
    (void)v;
}

void emu_outputs_zero(void)
{
#ifdef EMU_AD7606
    ad7606_zero();
#endif
#ifdef EMU_DAC
    dac_zero();
#endif
#ifdef EMU_ENCODER
    encoder_hold();
#endif
}
