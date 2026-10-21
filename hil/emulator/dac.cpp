// Emulated current sensors for current_sense = internal: MCP4922 x 2 (or MCP4921 x 4) written by LPSPI4 as an SPI
// master on Teensy 13 (SCK) and 11 (SDO), chip selects on 24, 25 (+28, 29), one shared LDAC on 30.
//
// Channels: MCP4922 x 2: DAC 1 (CS 24) A = phase A, B = phase C; DAC 2 (CS 25) A = phase B, B = phase D, as the
// wiring's analog rows. MCP4921 x 4: DAC k (CS 24, 25, 28, 29) = phase k. Each step writes one 16-bit word per phase
// (mode 0,0, 20 MHz, the MCP492x maximum), one chip-select frame each, driven by the LPSPI transfer-complete interrupt
// (priority EMU_PRIO_ENCODER), then pulses LDAC so all channels change together. A step that finds the previous
// sequence still running leaves its words for the end of that sequence (the latest words win).
//
// Safety: SCK and SDO share wires with the controller's AD7606 bus. The SPI peripheral always runs, but its pads are
// switched onto the wires only at the start of a sequence while the RUN input itself is high (the self-test does not
// count); the RUN falling edge (combined GPIO interrupt, priority 0) switches them back to GPIO inputs and raises
// every chip select at once. While RUN is low the DACs therefore hold the last code written while it was high.
#include <Arduino.h>
#include <math.h>

#include "emu.h"
extern "C" {
#include "hil_chips.h"
}

#ifdef EMU_DAC

#define PIN_LDAC 30
#define SCK_HZ 20000000.0
#define TCR_WORD (LPSPI_TCR_RXMSK | LPSPI_TCR_FRAMESZ(15))
#define MUX_SPI (3 | 0x10)       // ALT3: LPSPI4 SCK / SDO
#define MUX_GPIO (5 | 0x10)      // ALT5: GPIO, an input here
#define VREF 3.3f

#ifdef HIL_DAC_MCP4921X4
static const uint8_t CS_PIN[4] = {24, 25, 28, 29};
static const uint8_t SEQ_CS[4] = {0, 1, 2, 3}, SEQ_CH[4] = {0, 0, 0, 0}, SEQ_PHASE[4] = {0, 1, 2, 3};
#else
static const uint8_t CS_PIN[2] = {24, 25};
static const uint8_t SEQ_CS[4] = {0, 0, 1, 1}, SEQ_CH[4] = {0, 1, 0, 1}, SEQ_PHASE[4] = {0, 2, 1, 3};
#endif
#define N_CS (sizeof CS_PIN)

static float k_a, k_b;                    // code = k_a + k_b * amps
static uint16_t zero_code = 0;
static uint16_t hdr[4];                   // command bits of each sequence word (mcp492x_word with code 0)
static int q;
static uint16_t seq_words[4], next_words[4];
static uint8_t seq_n, seq_i, next_n;
static volatile bool busy, pending, wire;

static inline void cs_write(uint8_t j, bool level)
{
    switch (CS_PIN[j]) {       // constant pins, so each is one store
    case 24: digitalWriteFast(24, level); break;
    case 25: digitalWriteFast(25, level); break;
    case 28: digitalWriteFast(28, level); break;
    case 29: digitalWriteFast(29, level); break;
    }
}

static inline void cs_all_high()
{
    for (unsigned j = 0; j < N_CS; j++) cs_write(j, HIGH);
}

static void release()
{
    CORE_PIN13_CONFIG = MUX_GPIO;
    CORE_PIN11_CONFIG = MUX_GPIO;
    wire = false;
    cs_all_high();
}

// Interrupts disabled. The pads go onto the wires only here, with RUN read in the same critical section as the mux.
static void seq_start()
{
    if (GPIO7_PSR & CORE_PIN7_BITMASK) {
        if (!wire) {
            CORE_PIN13_CONFIG = MUX_SPI;
            CORE_PIN11_CONFIG = MUX_SPI;
            wire = true;
        }
    } else if (wire) {
        release();
    }
    busy = true;
    seq_i = 0;
    if (wire) cs_write(SEQ_CS[0], LOW);
    LPSPI4_TDR = seq_words[0];
}

// A chip select goes low only with interrupts disabled and the pads on the wires, so the RUN falling edge cannot
// leave one low; raising one is always safe.
static void spi_isr()
{
    LPSPI4_SR = LPSPI_SR_TCF;
    cs_write(SEQ_CS[seq_i], HIGH);
    if (++seq_i < seq_n) {
        delayNanoseconds(20);                           // CS high time (15 ns min)
        __disable_irq();
        if (wire) cs_write(SEQ_CS[seq_i], LOW);
        __enable_irq();
        LPSPI4_TDR = seq_words[seq_i];
    } else {
        if (wire) {
            delayNanoseconds(40);                       // CS high to LDAC low (40 ns min)
            digitalWriteFast(PIN_LDAC, LOW);
            delayNanoseconds(100);                      // LDAC pulse (100 ns min)
            digitalWriteFast(PIN_LDAC, HIGH);
        }
        __disable_irq();
        busy = false;
        if (pending) {
            pending = false;
            for (int j = 0; j < next_n; j++) seq_words[j] = next_words[j];
            seq_n = next_n;
            seq_start();
        }
        __enable_irq();
    }
    asm volatile("dsb");
}

void dac_begin(void)
{
    pinMode(13, INPUT);
    pinMode(11, INPUT);
    for (unsigned j = 0; j < N_CS; j++) pinMode(CS_PIN[j], OUTPUT);
    cs_all_high();
    pinMode(PIN_LDAC, OUTPUT);
    digitalWriteFast(PIN_LDAC, HIGH);
    release();

    // LPSPI4 master, the clock root as the Teensy SPI library sets it: PLL3 PFD0 (720 MHz) / 3 = 240 MHz.
    CCM_CCGR1 &= ~CCM_CCGR1_LPSPI4(CCM_CCGR_ON);
    CCM_CBCMR = (CCM_CBCMR & ~(CCM_CBCMR_LPSPI_PODF_MASK | CCM_CBCMR_LPSPI_CLK_SEL_MASK)) | CCM_CBCMR_LPSPI_PODF(2) |
                CCM_CBCMR_LPSPI_CLK_SEL(1);
    CCM_CCGR1 |= CCM_CCGR1_LPSPI4(CCM_CCGR_ON);
    const uint32_t fastio = IOMUXC_PAD_DSE(7) | IOMUXC_PAD_SPEED(2);
    CORE_PIN11_PADCONFIG = fastio;
    CORE_PIN13_PADCONFIG = fastio;
    const uint32_t div = (uint32_t)ceil(240e6 / SCK_HZ);      // SCK = root / (SCKDIV + 2)
    LPSPI4_CR = LPSPI_CR_RST;
    LPSPI4_CR = 0;
    LPSPI4_CFGR1 = LPSPI_CFGR1_MASTER;
    LPSPI4_CCR = LPSPI_CCR_SCKDIV(div - 2);
    LPSPI4_FCR = 0;
    LPSPI4_IER = LPSPI_IER_TCIE;
    attachInterruptVector(IRQ_LPSPI4, spi_isr);
    NVIC_SET_PRIORITY(IRQ_LPSPI4, EMU_PRIO_ENCODER);
    NVIC_ENABLE_IRQ(IRQ_LPSPI4);
    LPSPI4_CR = LPSPI_CR_MEN;
    LPSPI4_TCR = TCR_WORD;
}

const char *dac_configure(const hil_emu_config_t *c)
{
    if (!isfinite(c->dac_v_mid) || !isfinite(c->dac_v_per_a)) return "config refused: dac_v_mid or dac_v_per_a";
    k_a = c->dac_v_mid / VREF * 4096.0f;
    k_b = c->dac_v_per_a / VREF * 4096.0f;
    zero_code = dac_code(0.0, (double)c->dac_v_mid, (double)c->dac_v_per_a, (double)VREF);
    q = c->n_phases;
    for (int j = 0; j < 4; j++) hdr[j] = mcp492x_word(SEQ_CH[j], 0);
    return NULL;
}

// Code for k_a + k_b * amps rounded half away from zero and clipped to 0..4095, as hil_chips.c dac_code.
static inline uint16_t code12(float amps)
{
    const float x = k_a + k_b * amps;
    int32_t n = (int32_t)(x + copysignf(0.5f, x));
    asm("usat %0, #12, %1" : "=r"(n) : "r"(n));
    return (uint16_t)n;
}

static void submit(const uint16_t *code)
{
    uint16_t w[4];
    uint8_t n = 0;
    for (int j = 0; j < 4; j++)
        if (SEQ_PHASE[j] < q) w[n++] = hdr[j] | code[SEQ_PHASE[j]];      // codes are 12-bit
    __disable_irq();
    if (busy) {
        for (int j = 0; j < n; j++) next_words[j] = w[j];
        next_n = n;
        pending = true;
    } else {
        for (int j = 0; j < n; j++) seq_words[j] = w[j];
        seq_n = n;
        if (n) seq_start();
    }
    __enable_irq();
}

void dac_update(const srm_plant_t *p)
{
    uint16_t code[4] = {zero_code, zero_code, zero_code, zero_code};
    for (int k = 0; k < q; k++) code[k] = code12(p->cur[k]);
    submit(code);
}

void dac_zero(void)
{
    const uint16_t code[4] = {zero_code, zero_code, zero_code, zero_code};
    submit(code);
}

void dac_run_low(void) { release(); }

#endif
