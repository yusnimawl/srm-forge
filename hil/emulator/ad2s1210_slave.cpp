// Emulated AD2S1210 resolver-to-digital converter (position = ad2s1210 or both): LPSPI3 as an SPI slave on Teensy 0
// (WR/FSYNC as PCS0), 27 (SCLK), 1 (SDI), 26 (SDO); SAMPLE on pin 9 and A0/A1 on pins 22/23 (outputs.cpp).
//
// Each step computes the position and velocity words of the plant state after the step. The electrical angle x is
// resolver_pole_pairs times the measured angle of the SIL sensor model (encoder offset and eccentricity,
// outputs.cpp measured_turns); with a gain mismatch g or a phase error phi it becomes
// atan2(sin x, (1 + g) cos(x + phi)), the angle the converter tracks from the SIL's imperfect sin/cos. That error is a
// function of x alone, tabulated at the config (ERR_TAB points over an electrical turn, linear interpolation: about
// 1e-7 turn at 5 % gain and 0.05 rad phase error, 1/150 of a 16-bit count), so a step costs no trigonometry. Velocity is resolver_pole_pairs * omega in two's complement, full scale +-2500, 1000,
// 500 or 125 rps at 10, 12, 14 or 16 bits (the datasheet's values for an 8.192 MHz clock).
//
// SAMPLE falling edge latches both words. A0/A1 select the output as on the chip: (0, 0) position, (0, 1) velocity,
// (1, 1) configuration. In normal mode a frame is 24 bits, the 16-bit word (MSB-aligned at the resolution) then the
// fault register (0); the latched word is queued 8 times, so it can be read again until the next SAMPLE or A0/A1
// change. In configuration mode frames are 8 bits: a byte with bit 7 set is an address and the next frame returns that
// register; a byte with bit 7 clear is written to the last address. Only the control register (0x92) RES1/RES0
// (10, 12, 14, 16 bits) is used. SPI mode 3 (CPOL 1, CPHA 1). SDO is tri-stated with WR/FSYNC high.
#include <Arduino.h>
#include <math.h>

#include "emu.h"
extern "C" {
#include "hil_chips.h"
}

#ifdef EMU_RDC

#define PIN_RDC_A0 22
#define PIN_RDC_A1 23
#define REG_CONTROL 0x92
#define NORMAL_COPIES 8
#define TCR_NORMAL (LPSPI_TCR_CPOL | LPSPI_TCR_CPHA | LPSPI_TCR_RXMSK | LPSPI_TCR_FRAMESZ(23))
#define TCR_CONFIG (LPSPI_TCR_CPOL | LPSPI_TCR_CPHA | LPSPI_TCR_FRAMESZ(7))

static uint8_t reg[128];
static volatile uint8_t addr;           // last address byte, 0 = none
static volatile int bits;
#define ERR_TAB 1024
static double pp;
static bool errors;
static float err_tab[ERR_TAB + 1];      // tracked minus true electrical angle, in turns
static float vel_omega = NAN;           // omega and resolution of the cached velocity word
static int vel_bits;
static uint16_t vel_word;
static uint16_t words[2][2];            // [buffer][position, velocity]; the SAMPLE interrupt reads words[cur]
static volatile uint8_t cur;
static uint16_t latched[2];

static int res_bits(uint8_t control) { return 10 + 2 * (control & 3); }
static double max_rps(int b) { return b <= 10 ? 2500.0 : b <= 12 ? 1000.0 : b <= 14 ? 500.0 : 125.0; }

static void load_normal(bool velocity)
{
    LPSPI3_CR = LPSPI_CR_MEN | LPSPI_CR_RTF | LPSPI_CR_RRF;
    LPSPI3_SR = LPSPI_SR_TEF | LPSPI_SR_REF | LPSPI_SR_FCF | LPSPI_SR_TCF | LPSPI_SR_WCF;
    LPSPI3_IER = 0;
    LPSPI3_TCR = TCR_NORMAL;
    const uint32_t w = (uint32_t)latched[velocity ? 1 : 0] << 8;     // fault register 0
    for (int j = 0; j < NORMAL_COPIES; j++) LPSPI3_TDR = w;
}

static void load_config()
{
    LPSPI3_CR = LPSPI_CR_MEN | LPSPI_CR_RTF | LPSPI_CR_RRF;
    LPSPI3_SR = LPSPI_SR_TEF | LPSPI_SR_REF | LPSPI_SR_FCF | LPSPI_SR_TCF | LPSPI_SR_WCF;
    LPSPI3_TCR = TCR_CONFIG;
    LPSPI3_TDR = 0;
    addr = 0;
    LPSPI3_IER = LPSPI_IER_RDIE;
}

// Configuration-mode bytes (priority EMU_PRIO_ENCODER).
static void spi_isr()
{
    while (!(LPSPI3_RSR & LPSPI_RSR_RXEMPTY)) {
        const uint8_t b = (uint8_t)LPSPI3_RDR;
        if (b & 0x80) {
            addr = b;
            LPSPI3_TDR = reg[b & 0x7F];
        } else {
            if (addr) {
                reg[addr & 0x7F] = b;
                if (addr == REG_CONTROL) bits = res_bits(b);
            }
            LPSPI3_TDR = 0;
        }
    }
    asm volatile("dsb");
}

void rdc_begin(void)
{
    CCM_CCGR1 &= ~CCM_CCGR1_LPSPI3(CCM_CCGR_ON);
    CCM_CBCMR = (CCM_CBCMR & ~(CCM_CBCMR_LPSPI_PODF_MASK | CCM_CBCMR_LPSPI_CLK_SEL_MASK)) | CCM_CBCMR_LPSPI_PODF(2) |
                CCM_CBCMR_LPSPI_CLK_SEL(1);
    CCM_CCGR1 |= CCM_CCGR1_LPSPI3(CCM_CCGR_ON);
    const uint32_t fastio = IOMUXC_PAD_DSE(7) | IOMUXC_PAD_SPEED(2);
    CORE_PIN26_PADCONFIG = fastio;
    CORE_PIN0_CONFIG = 7 | 0x10;        // ALT7 LPSPI3_PCS0
    CORE_PIN1_CONFIG = 7 | 0x10;        // ALT7 LPSPI3_SDI
    CORE_PIN26_CONFIG = 2 | 0x10;       // ALT2 LPSPI3_SDO
    CORE_PIN27_CONFIG = 2 | 0x10;       // ALT2 LPSPI3_SCK
    IOMUXC_LPSPI3_PCS0_SELECT_INPUT = 0;
    IOMUXC_LPSPI3_SDI_SELECT_INPUT = 0;
    IOMUXC_LPSPI3_SDO_SELECT_INPUT = 1;
    IOMUXC_LPSPI3_SCK_SELECT_INPUT = 1;
    LPSPI3_CR = LPSPI_CR_RST;
    LPSPI3_CR = 0;
    LPSPI3_CFGR1 = LPSPI_CFGR1_OUTCFG;  // slave, PCS0 active low, SDI in / SDO out
    LPSPI3_FCR = 0;
    LPSPI3_IER = 0;
    attachInterruptVector(IRQ_LPSPI3, spi_isr);
    NVIC_SET_PRIORITY(IRQ_LPSPI3, EMU_PRIO_ENCODER);
    NVIC_ENABLE_IRQ(IRQ_LPSPI3);
    LPSPI3_CR = LPSPI_CR_MEN;
    load_normal(false);
}

const char *rdc_configure(const hil_emu_config_t *c)
{
    if (c->rdc_bits < 10 || c->rdc_bits > 16 || (c->rdc_bits & 1)) return "config refused: rdc_bits must be 10, 12, 14 or 16";
    if (c->resolver_pole_pairs < 1) return "config refused: resolver_pole_pairs";
    if (!isfinite(c->resolver_gain_mismatch) || !isfinite(c->resolver_phase_error) ||
        !(fabsf(c->resolver_gain_mismatch) < 0.5f))
        return "config refused: resolver errors";
    pp = c->resolver_pole_pairs;
    errors = c->resolver_gain_mismatch != 0.0f || c->resolver_phase_error != 0.0f;
    const double g = 1.0 + (double)c->resolver_gain_mismatch, phi = c->resolver_phase_error;
    for (int j = 0; j <= ERR_TAB; j++) {
        const double x = 2.0 * M_PI * j / ERR_TAB, a = atan2(sin(x), g * cos(x + phi));
        err_tab[j] = (float)(remainder(a - x, 2.0 * M_PI) / (2.0 * M_PI));
    }
    reg[REG_CONTROL & 0x7F] = (uint8_t)(0x70 | ((c->rdc_bits - 10) / 2));
    return NULL;
}

void rdc_update(double turns, float omega)
{
    const int b = bits;
    double e = pp * turns;
    e -= floor(e);
    if (errors) {
        const float f = (float)e * ERR_TAB;
        const int i = f < (float)ERR_TAB ? (int)f : ERR_TAB - 1;    // e rounded to float may reach 1
        e += (double)(err_tab[i] + (f - (float)i) * (err_tab[i + 1] - err_tab[i]));
    }
    if (omega != vel_omega || b != vel_bits) {      // constant at fixed speed
        vel_word = (uint16_t)ad2s1210_velocity(pp * (double)omega, b, max_rps(b));
        vel_omega = omega;
        vel_bits = b;
    }
    uint16_t *w = words[cur ^ 1];
    w[0] = ad2s1210_position_turns(e, b);
    w[1] = vel_word;
    __asm__ volatile("" ::: "memory");      // the words before the index that publishes them
    cur ^= 1;
}

void rdc_start(double turns, float omega)
{
    bits = res_bits(reg[REG_CONTROL & 0x7F]);
    vel_omega = NAN;
    latched[0] = latched[1] = 0;
    rdc_update(turns, omega);
    rdc_select();
}

void rdc_sample(void)
{
    latched[0] = words[cur][0];
    latched[1] = words[cur][1];
    rdc_select();
}

void rdc_select(void)
{
    const bool a0 = digitalReadFast(PIN_RDC_A0), a1 = digitalReadFast(PIN_RDC_A1);
    if (a0 && a1) load_config();
    else load_normal(a1);
}

#endif
