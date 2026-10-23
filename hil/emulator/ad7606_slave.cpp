// Emulated AD7606 (current_sense = ad7606): LPSPI4 as an SPI slave on Teensy 10 (CS), 13 (SCK), 11 (DOUTA, the
// LPSPI SDO pad); CONVST in on pin 5 (rising edge), BUSY out on pin 6.
//
// Each step stores the 8 channel codes of the plant state after the step: V1-V4 the phase currents times
// sense_v_per_a, V5-V8 the phase voltages (averaged over the step) times volt_divider through a first-order filter of
// time constant volt_rc_tau; 16-bit two's complement over +-ad7606_range_v (5 or 10 V), rounded half away from zero
// and clipped, as hil_chips.c ad7606_code (computed here in single precision with the gains folded together).
// SPI mode 2 (CPOL 1, CPHA 0): DB15 is out when CS falls and the controller samples on SCK falling edges. With CS high
// the slave's SDO is tri-stated (CFGR1.OUTCFG = 1), so the wire is free for other modes.
//
// CONVST: pin 5 is XBAR1 input 17 (ALT3), routed by XBAR1 to QTIMER4 timer 1 (output 99, GPR6
// QTIMER4_TRM1_INPUT_SEL), whose output is pin 6 (ALT1). The timer makes BUSY in hardware: it rises at the edge and
// falls ad7606_t_conv_us later (triggered count up to COMP1 on the IP bus clock, then re-armed); an edge during BUSY
// restarts it (CSCTRL.TCI). The same edge sets the timer's input edge flag, whose interrupt (convst_isr) loads the
// latest codes into the transmit FIFO as one 128-bit frame (V1 first, MSB first) and stamps the trigger.
// The frame is loaded by the CPU. An eDMA version worked on the wire, but at 1008 MHz (IP bus 252 MHz) any eDMA
// activity, even one RAM-to-RAM copy per CONVST, made the step interrupt's PIT read take a bus fault within minutes,
// and so did CPU reads of the eDMA registers (docs/r8b-hil-results.md, Step 1c). That clock fails timing (Step 1d);
// the eDMA was not tried again at 912 MHz.
#include <Arduino.h>
#include <math.h>

#include "emu.h"

#ifdef EMU_AD7606

#define N_CH 8
#define TCR_FRAME (LPSPI_TCR_CPOL | LPSPI_TCR_RXMSK | LPSPI_TCR_FRAMESZ(16 * N_CH - 1))
#define XBAR_IN_CONVST 17          // XBAR1_INOUT17: pin 5 (GPIO_EMC_08 ALT3)
#define BUSY_MIN_US 1.0
// BUSY as the inverted OFLAG (set at compare: pin low), input edge flag on rising edges with its interrupt
#define SCTRL_BUSY (TMR_SCTRL_OPS | TMR_SCTRL_VAL | TMR_SCTRL_OEN | TMR_SCTRL_CAPTURE_MODE(1) | TMR_SCTRL_IEFIE)

static uint32_t words[2][N_CH / 2];     // double buffer; the CONVST interrupt reads words[cur]
static volatile uint8_t cur;
static float k_i, k_v, alpha, vf[EMU_MAX_PHASES];
static int q;

static void xbar_route(unsigned input, unsigned output)
{
    volatile uint16_t *sel = &XBARA1_SEL0 + output / 2;     // 16-bit access only
    *sel = (uint16_t)(output & 1 ? (*sel & 0x00FF) | input << 8 : (*sel & 0xFF00) | input);
}

// CONVST rising edge (BUSY is already high): clear the edge flag, load the frame, stamp the trigger.
static void convst_isr()
{
    const uint32_t t = ARM_DWT_CYCCNT;
    TMR4_SCTRL1 = SCTRL_BUSY;                     // IEF = 0
    const uint32_t *w = words[cur];
    LPSPI4_CR = LPSPI_CR_MEN | LPSPI_CR_RTF;      // drop an unread frame
    LPSPI4_SR = LPSPI_SR_TEF | LPSPI_SR_REF | LPSPI_SR_FCF | LPSPI_SR_TCF | LPSPI_SR_WCF;
    LPSPI4_TCR = TCR_FRAME;
    for (int j = 0; j < N_CH / 2; j++) LPSPI4_TDR = w[j];
    outputs_trigger_stamp(t);
    asm volatile("dsb");
}

void ad7606_begin(void)
{
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

    // BUSY: QTIMER4 timer 1 (the core's PWM setup configured it at boot; every register is set here). The output is
    // the inverted OFLAG: forced to 1 (pin low), cleared by the CONVST edge (pin high), set again at compare.
    CCM_CCGR6 |= CCM_CCGR6_QTIMER4(CCM_CCGR_ON);
    TMR4_CTRL1 = 0;
    TMR4_SCTRL1 = TMR_SCTRL_OPS | TMR_SCTRL_VAL;
    TMR4_SCTRL1 = TMR_SCTRL_OPS | TMR_SCTRL_VAL | TMR_SCTRL_FORCE;
    TMR4_CSCTRL1 = 0;
    TMR4_FILT1 = 0;
    TMR4_DMA1 = 0;
    TMR4_LOAD1 = 0;
    TMR4_CNTR1 = 0;
    TMR4_COMP11 = 0xFFFF;
    TMR4_CMPLD11 = 0xFFFF;
    TMR4_ENBL |= 1u << 1;
    IOMUXC_GPR_GPR6 |= IOMUXC_GPR_GPR6_QTIMER4_TRM1_INPUT_SEL;     // timer 1 input from XBAR1 output 99
    TMR4_SCTRL1 = TMR_SCTRL_OPS | TMR_SCTRL_VAL | TMR_SCTRL_OEN;
    CORE_PIN6_PADCONFIG = IOMUXC_PAD_DSE(7);
    CORE_PIN6_CONFIG = 1;               // ALT1 QTIMER4_TIMER1
    attachInterruptVector(IRQ_QTIMER4, convst_isr);
    NVIC_SET_PRIORITY(IRQ_QTIMER4, EMU_PRIO_GATES);
    NVIC_ENABLE_IRQ(IRQ_QTIMER4);

    // XBAR1: pin 5 to the timer.
    CCM_CCGR2 |= CCM_CCGR2_XBAR1(CCM_CCGR_ON);
    xbar_route(XBAR_IN_CONVST, XBARA1_OUT_QTIMER4_TIMER1);
    IOMUXC_GPR_GPR6 &= ~IOMUXC_GPR_GPR6_IOMUXC_XBAR_DIR_SEL_17;    // XBAR1_INOUT17 is an input
    CORE_PIN5_PADCONFIG = IOMUXC_PAD_DSE(7) | IOMUXC_PAD_PKE | IOMUXC_PAD_PUE | IOMUXC_PAD_PUS(0) | IOMUXC_PAD_HYS;
    IOMUXC_XBAR1_IN17_SELECT_INPUT = 0;  // GPIO_EMC_08
    CORE_PIN5_CONFIG = 3;               // ALT3 XBAR1_INOUT17
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
    q = c->n_phases;
    // BUSY width in IP bus clocks, prescaled by 2^p into the 16-bit compare. At least BUSY_MIN_US, so the CONVST
    // interrupt has loaded the frame before BUSY falls and the controller reads it.
    const double t_conv = fmax((double)c->ad7606_t_conv_us, BUSY_MIN_US);
    uint32_t ticks = (uint32_t)lround(t_conv * 1e-6 * F_BUS_ACTUAL), p = 0;
    while ((ticks + (1u << p >> 1)) >> p > 0x10000u) p++;
    ticks = (ticks + (1u << p >> 1)) >> p;
    TMR4_CTRL1 = 0;
    TMR4_CNTR1 = 0;
    TMR4_COMP11 = (uint16_t)(ticks - 1);
    TMR4_CMPLD11 = (uint16_t)(ticks - 1);
    TMR4_SCTRL1 = SCTRL_BUSY | TMR_SCTRL_FORCE;      // BUSY low
    TMR4_CSCTRL1 = TMR_CSCTRL_TCI;
    TMR4_CTRL1 = TMR_CTRL_CM(6) | TMR_CTRL_PCS(8 + p) | TMR_CTRL_SCS(1) | TMR_CTRL_LENGTH | TMR_CTRL_OUTMODE(5);
    return NULL;
}

static void publish(const int16_t *code)
{
    uint32_t *w = words[cur ^ 1];
    for (int j = 0; j < N_CH / 2; j++) w[j] = (uint32_t)(uint16_t)code[2 * j] << 16 | (uint16_t)code[2 * j + 1];
    __asm__ volatile("" ::: "memory");      // the words before the index that publishes them
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

#endif
