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

static void edge_irq(uint8_t pin, volatile uint32_t &edge_sel, volatile uint32_t &isr, volatile uint32_t &imr,
                     uint32_t mask, uint32_t &bits)
{
    pinMode(pin, INPUT_PULLDOWN);
    edge_sel |= mask;
    isr = mask;
    imr |= mask;
    bits |= mask;
}

void outputs_begin(void)
{
    for (int j = 0; j <= SIN_TAB; j++) sin_tab[j] = (float)sin(2.0 * M_PI * j / SIN_TAB);
#ifdef EMU_AD7606
    ad7606_begin();
    edge_irq(PIN_CONVST, GPIO9_EDGE_SEL, GPIO9_ISR, GPIO9_IMR, CORE_PIN5_BITMASK, bits9);
#endif
#ifdef EMU_DAC
    dac_begin();
    edge_irq(PIN_RUN, GPIO7_EDGE_SEL, GPIO7_ISR, GPIO7_IMR, CORE_PIN7_BITMASK, bits7);
#endif
#ifdef EMU_RDC
    rdc_begin();
    edge_irq(PIN_SAMPLE, GPIO7_EDGE_SEL, GPIO7_ISR, GPIO7_IMR, CORE_PIN9_BITMASK, bits7);
    edge_irq(PIN_RDC_A0, GPIO6_EDGE_SEL, GPIO6_ISR, GPIO6_IMR, CORE_PIN22_BITMASK, bits6);
    edge_irq(PIN_RDC_A1, GPIO6_EDGE_SEL, GPIO6_ISR, GPIO6_IMR, CORE_PIN23_BITMASK, bits6);
#endif
#ifdef EMU_ENCODER
    encoder_begin();
#endif
}

void outputs_pins_isr(void)
{
    const uint32_t f6 = GPIO6_ISR & bits6, f7 = GPIO7_ISR & bits7, f9 = GPIO9_ISR & bits9;
    if (f6) GPIO6_ISR = f6;
    if (f7) GPIO7_ISR = f7;
    if (f9) GPIO9_ISR = f9;
#ifdef EMU_DAC
    if ((f7 & CORE_PIN7_BITMASK) && !(GPIO7_PSR & CORE_PIN7_BITMASK)) dac_run_low();
#endif
#ifdef EMU_AD7606
    if ((f9 & CORE_PIN5_BITMASK) && (GPIO9_PSR & CORE_PIN5_BITMASK)) ad7606_convst();
#endif
#ifdef EMU_RDC
    if ((f7 & CORE_PIN9_BITMASK) && !(GPIO7_PSR & CORE_PIN9_BITMASK)) rdc_sample();
    if (f6) rdc_select();
#endif
}

const char *outputs_configure(const hil_emu_config_t *c)
{
    if (!isfinite(c->encoder_offset) || !isfinite(c->encoder_ecc_amp) ||
        (c->encoder_ecc_amp != 0.0f && c->encoder_ecc_harmonic < 1))
        return "config refused: encoder offset or eccentricity";
    off_turns = c->encoder_offset / (2.0 * M_PI);
    ecc_turns = c->encoder_ecc_amp / (2.0 * M_PI);
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
