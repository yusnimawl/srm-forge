/* Gate PWM of the asymmetric half-bridge: TIM1 CH1..CH4 = upper switches A..D (PE9, PE11, PE13, PE14, AF1),
 * TIM8 CH1..CH4 = lower switches A..D (PC6..PC9, AF3), independent channels (not CHxN), no dead time (an AHB phase
 * has no shoot-through path).
 *
 * Both timers count 0..ARR..0 (centre-aligned) from the 200 MHz kernel clock in PWM mode 1 with compare preload, so
 * ARR = 200 MHz / (2 pwm_hz) and new compare values take effect at the next update event. The repetition counter
 * (RCR = half periods per ISR period - 1) is loaded by an update generation before the counters start; the counter
 * then reaches the first overflow with a non-zero repetition count, so the update events fall on the underflows
 * (measured on the board: an RCR written after the start puts them on the overflows). pwm_init checks the phase on
 * both timers (pwm_phase_ok). TIM1 is the master: TRGO = counter enable
 * starts TIM8 (trigger mode on ITR0 = tim1_trgo), TRGO2 = update triggers the internal ADCs. The update interrupt of
 * TIM1 is the sample trigger (srm_hal_stm32.c).
 *
 * Off state: MOE = 0 with OSSI = 1 and OISx = 0 drives every gate low. pwm_kill clears MOE (immediate) and zeroes the
 * compares; pwm_enable sets MOE. */
#include "srm_hal_stm32.h"

#include "hil_config.h"
#include "pwm_compare.h"

static uint16_t arr;
static bool phase_ok;
volatile int32_t pwm_skew_ticks;       /* TIM1 minus TIM8 count just after the start (read by the debugger) */

#define OC_PWM1_PRELOAD(ch) ((6u << TIM_CCMR1_OC1M_Pos | TIM_CCMR1_OC1PE) << ((ch) * 8u))
#define BDTR_OFF (TIM_BDTR_OSSI | TIM_BDTR_OSSR)

static void gate_pins(uint32_t mode)
{
    GPIO_InitTypeDef g = {0};
    g.Mode = mode;
    g.Pull = GPIO_PULLDOWN;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    g.Pin = GPIO_PIN_9 | GPIO_PIN_11 | GPIO_PIN_13 | GPIO_PIN_14;
    g.Alternate = GPIO_AF1_TIM1;
    HAL_GPIO_Init(GPIOE, &g);
    g.Pin = GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9;
    g.Alternate = GPIO_AF3_TIM8;
    HAL_GPIO_Init(GPIOC, &g);
}

static void timer_setup(TIM_TypeDef *t, uint32_t rcr)
{
    t->CR1 = 0;
    t->PSC = 0;
    t->ARR = arr;
    t->RCR = rcr;
    t->CCMR1 = OC_PWM1_PRELOAD(0) | OC_PWM1_PRELOAD(1);
    t->CCMR2 = OC_PWM1_PRELOAD(0) | OC_PWM1_PRELOAD(1);
    t->CCR1 = t->CCR2 = t->CCR3 = t->CCR4 = 0;
    t->CCER = TIM_CCER_CC1E | TIM_CCER_CC2E | TIM_CCER_CC3E | TIM_CCER_CC4E;
    t->BDTR = BDTR_OFF;
    t->CR1 = TIM_CR1_CMS_0 | TIM_CR1_ARPE;
    t->EGR = TIM_EGR_UG;
    t->SR = 0;
}

/* Wait for the next update of t and report whether it came at the underflow (counting up afterwards). */
static bool update_at_underflow(TIM_TypeDef *t)
{
    t->SR = ~TIM_SR_UIF;
    const uint32_t t0 = DWT->CYCCNT;
    while (!(t->SR & TIM_SR_UIF))
        if (DWT->CYCCNT - t0 > DRV_CPU_HZ / 5u) return false;      /* 200 ms */
    return !(t->CR1 & TIM_CR1_DIR);
}

const char *pwm_init(float pwm_hz, float isr_hz)
{
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_9 | GPIO_PIN_11 | GPIO_PIN_13 | GPIO_PIN_14, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9, GPIO_PIN_RESET);
    gate_pins(GPIO_MODE_OUTPUT_PP);

    if (!(pwm_hz > 0.0f) || !(isr_hz > 0.0f)) return "setup refused: pwm_hz and isr_hz must be positive";
    const float a = (float)DRV_TIMER_HZ / (2.0f * pwm_hz);
    if (!(a >= 100.0f && a <= 65534.0f)) return "setup refused: pwm_hz out of range (1527 Hz .. 1 MHz)";
    const float halves = 2.0f * pwm_hz / isr_hz;     /* carrier half periods per ISR period */
    const uint32_t n = (uint32_t)(halves + 0.5f);
    if (!(halves > 0.5f) || n > 256u || (n != 1u && (n & 1u)) || halves - (float)n > 1e-3f * (float)n ||
        (float)n - halves > 1e-3f * (float)n)
        return "setup refused: isr_hz must be 2 x pwm_hz or pwm_hz / k (k = 1..128)";
    arr = (uint16_t)(a + 0.5f);

    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_TIM8_CLK_ENABLE();
    timer_setup(TIM1, n - 1u);
    timer_setup(TIM8, n - 1u);
    TIM1->CR2 = (1u << TIM_CR2_MMS_Pos) | (2u << TIM_CR2_MMS2_Pos);     /* TRGO enable, TRGO2 update */
    TIM8->CR2 = 0;
    TIM8->SMCR = (0u << TIM_SMCR_TS_Pos) | TIM_SMCR_SMS_2 | TIM_SMCR_SMS_1;   /* ITR0, trigger mode */
    gate_pins(GPIO_MODE_AF_PP);

    TIM1->CR1 |= TIM_CR1_CEN;
    {
        const int32_t c1 = (int32_t)TIM1->CNT, c8 = (int32_t)TIM8->CNT, c1b = (int32_t)TIM1->CNT;
        pwm_skew_ticks = (c1 + c1b) / 2 - c8;
    }
    phase_ok = true;
    for (int k = 0; k < 3; k++) {
        const bool u1 = update_at_underflow(TIM1), u8 = update_at_underflow(TIM8);
        if (n != 1u && !(u1 && u8)) phase_ok = false;
    }
    TIM1->SR = 0;
    TIM1->DIER = TIM_DIER_UIE;
    HAL_NVIC_SetPriority(TIM1_UP_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(TIM1_UP_IRQn);
    return NULL;
}

uint16_t pwm_arr(void) { return arr; }
bool pwm_phase_ok(void) { return phase_ok; }

void pwm_set_switches(uint8_t phase, bool upper, bool lower)
{
    if (phase >= HIL_N_PHASES || phase >= 4) return;
    const uint16_t on = (uint16_t)(arr + 1u);
    (&TIM1->CCR1)[phase] = upper ? on : 0u;
    (&TIM8->CCR1)[phase] = lower ? on : 0u;
}

void pwm_set_duty(uint8_t phase, float duty, srm_chop_t mode)
{
    if (phase >= HIL_N_PHASES || phase >= 4) return;
    uint16_t u, l;
    ahb_compare(duty, mode == SRM_CHOP_SOFT, arr, &u, &l);
    (&TIM1->CCR1)[phase] = u;
    (&TIM8->CCR1)[phase] = l;
}

void pwm_kill(void)
{
    TIM1->BDTR = BDTR_OFF;
    TIM8->BDTR = BDTR_OFF;
    for (int k = 0; k < 4; k++) {
        (&TIM1->CCR1)[k] = 0u;
        (&TIM8->CCR1)[k] = 0u;
    }
}

void pwm_enable(void)
{
    TIM1->BDTR = BDTR_OFF | TIM_BDTR_MOE;
    TIM8->BDTR = BDTR_OFF | TIM_BDTR_MOE;
}
