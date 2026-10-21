// Emulated AD7606 (current_sense = ad7606): LPSPI4 as an SPI slave on Teensy 10 (CS), 13 (SCK), 11 (DOUTA, the
// LPSPI SDO pad); CONVST on pin 5 (rising edge, outputs.cpp), BUSY out on pin 6.
//
// Each step stores the 8 channel codes of the plant state after the step: V1-V4 the phase currents times
// sense_v_per_a, V5-V8 the phase voltages (averaged over the step) times volt_divider through a first-order filter of
// time constant volt_rc_tau; 16-bit two's complement over +-ad7606_range_v (5 or 10 V), rounded half away from zero
// and clipped, as hil_chips.c ad7606_code (computed here in single precision with the gains folded together).
// CONVST loads the latest codes into the transmit FIFO as one 128-bit frame (V1 first, MSB first) and raises BUSY for
// ad7606_t_conv_us. SPI mode 2 (CPOL 1, CPHA 0): DB15 is out when CS falls and the controller samples on SCK falling
// edges. With CS high the slave's SDO is tri-stated (CFGR1.OUTCFG = 1), so the wire is free for other modes.
#include <Arduino.h>
#include <math.h>

#include "emu.h"

#ifdef EMU_AD7606

#define PIN_BUSY 6
#define PIN_CS 10
#define PIN_SCK 13
#define PIN_SDO 11
#define N_CH 8
#define TCR_FRAME (LPSPI_TCR_CPOL | LPSPI_TCR_RXMSK | LPSPI_TCR_FRAMESZ(16 * N_CH - 1))

static uint32_t words[2][N_CH / 2];     // double buffer; the CONVST interrupt reads words[cur]
static volatile uint8_t cur;
static float k_i, k_v, alpha, vf[EMU_MAX_PHASES];
static uint32_t t_conv_ticks;
static int q;

static void busy_isr()
{
    GPT1_SR = GPT_SR_OF1;
    GPT1_IR = 0;
    digitalWriteFast(PIN_BUSY, LOW);
    asm volatile("dsb");
}

void ad7606_begin(void)
{
    pinMode(PIN_BUSY, OUTPUT);
    digitalWriteFast(PIN_BUSY, LOW);

    // BUSY timer: GPT1 free-running on the 24 MHz oscillator, compare 1.
    CCM_CCGR1 |= CCM_CCGR1_GPT1_BUS(CCM_CCGR_ON) | CCM_CCGR1_GPT1_SERIAL(CCM_CCGR_ON);
    GPT1_CR = 0;
    GPT1_CR = GPT_CR_SWR;
    while (GPT1_CR & GPT_CR_SWR) {}
    GPT1_PR = 0;
    GPT1_CR = GPT_CR_CLKSRC(5) | GPT_CR_EN_24M | GPT_CR_FRR | GPT_CR_ENMOD;
    GPT1_CR |= GPT_CR_EN;
    GPT1_IR = 0;
    attachInterruptVector(IRQ_GPT1, busy_isr);
    NVIC_SET_PRIORITY(IRQ_GPT1, EMU_PRIO_ENCODER);
    NVIC_ENABLE_IRQ(IRQ_GPT1);

    // LPSPI4 slave; the clock root as the Teensy SPI library sets it (PLL3 PFD0 / 3).
    CCM_CCGR1 &= ~CCM_CCGR1_LPSPI4(CCM_CCGR_ON);
    CCM_CBCMR = (CCM_CBCMR & ~(CCM_CBCMR_LPSPI_PODF_MASK | CCM_CBCMR_LPSPI_CLK_SEL_MASK)) | CCM_CBCMR_LPSPI_PODF(2) |
                CCM_CBCMR_LPSPI_CLK_SEL(1);
    CCM_CCGR1 |= CCM_CCGR1_LPSPI4(CCM_CCGR_ON);
    const uint32_t fastio = IOMUXC_PAD_DSE(7) | IOMUXC_PAD_SPEED(2);
    CORE_PIN11_PADCONFIG = fastio;
    CORE_PIN13_PADCONFIG = fastio;
    CORE_PIN10_PADCONFIG = fastio;
    CORE_PIN11_CONFIG = 3 | 0x10;       // ALT3 LPSPI4_SDO
    CORE_PIN13_CONFIG = 3 | 0x10;       // ALT3 LPSPI4_SCK
    CORE_PIN10_CONFIG = 3 | 0x10;       // ALT3 LPSPI4_PCS0
    IOMUXC_LPSPI4_SCK_SELECT_INPUT = 0;
    IOMUXC_LPSPI4_SDO_SELECT_INPUT = 0;
    IOMUXC_LPSPI4_PCS0_SELECT_INPUT = 0;
    LPSPI4_CR = LPSPI_CR_RST;
    LPSPI4_CR = 0;
    LPSPI4_CFGR1 = LPSPI_CFGR1_OUTCFG;  // slave (MASTER = 0), PCS0 active low, SDI in / SDO out (PINCFG 0)
    LPSPI4_FCR = 0;
    LPSPI4_IER = 0;
    LPSPI4_CR = LPSPI_CR_MEN;
    LPSPI4_TCR = TCR_FRAME;
}

const char *ad7606_configure(const hil_emu_config_t *c)
{
    if (c->ad7606_range_v != 5.0f && c->ad7606_range_v != 10.0f) return "config refused: ad7606_range_v must be 5 or 10";
    if (!(c->ad7606_t_conv_us >= 0.0f && c->ad7606_t_conv_us <= 1000.0f))
        return "config refused: ad7606_t_conv_us must be 0..1000";
    if (!isfinite(c->sense_v_per_a) || !isfinite(c->volt_divider) || !(c->volt_rc_tau >= 0.0f) ||
        !isfinite(c->volt_rc_tau))
        return "config refused: sense_v_per_a, volt_divider or volt_rc_tau";
    const float lsb = 32768.0f / c->ad7606_range_v;
    k_i = c->sense_v_per_a * lsb;
    k_v = c->volt_divider * lsb;
    alpha = c->volt_rc_tau > 0.0f ? (float)(1.0 - exp(-EMU_DT / (double)c->volt_rc_tau)) : 1.0f;
    t_conv_ticks = (uint32_t)lround((double)c->ad7606_t_conv_us * 1e-6 * EMU_GPT_HZ);
    if (t_conv_ticks < 1) t_conv_ticks = 1;
    q = c->n_phases;
    return NULL;
}

static void publish(const int16_t *code)
{
    uint32_t *w = words[cur ^ 1];
    for (int j = 0; j < N_CH / 2; j++) w[j] = (uint32_t)(uint16_t)code[2 * j] << 16 | (uint16_t)code[2 * j + 1];
    cur ^= 1;
}

void ad7606_start(void)
{
    for (int k = 0; k < EMU_MAX_PHASES; k++) vf[k] = 0.0f;
    ad7606_zero();
}

void ad7606_update(const srm_plant_t *p, const srm_real_t *v)
{
    int16_t code[N_CH] = {0};
    for (int k = 0; k < q; k++) {
        vf[k] += alpha * (v[k] * k_v - vf[k]);
        code[k] = emu_sat16(p->cur[k] * k_i);
        code[4 + k] = emu_sat16(vf[k]);
    }
    publish(code);
}

void ad7606_zero(void)
{
    const int16_t code[N_CH] = {0};
    publish(code);
}

void ad7606_convst(void)
{
    const uint32_t *w = words[cur];
    LPSPI4_CR = LPSPI_CR_MEN | LPSPI_CR_RTF;      // drop an unread frame
    LPSPI4_SR = LPSPI_SR_TEF | LPSPI_SR_REF | LPSPI_SR_FCF | LPSPI_SR_TCF | LPSPI_SR_WCF;
    LPSPI4_TCR = TCR_FRAME;
    for (int j = 0; j < N_CH / 2; j++) LPSPI4_TDR = w[j];
    digitalWriteFast(PIN_BUSY, HIGH);
    GPT1_SR = GPT_SR_OF1;
    GPT1_OCR1 = GPT1_CNT + t_conv_ticks;
    GPT1_IR = GPT_IR_OF1IE;
}

#endif
