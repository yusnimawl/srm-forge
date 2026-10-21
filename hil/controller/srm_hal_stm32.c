/* srm_hal_t on the NUCLEO-H723ZG: the sample trigger, ctrl_isr scheduling and timing, RUN/READY, time base and
 * ctrl_slow. Layout and priorities: srm_hal_stm32.h. */
#include "srm_hal_stm32.h"

#include <math.h>
#include <setjmp.h>

#include "hil_config.h"
#include "srm_ctrl.h"

#if defined(HIL_CURRENT_SENSE_AD7606) == defined(HIL_CURRENT_SENSE_INTERNAL)
#error "hil_config.h selects no current sensing mode, or both"
#endif
#if !defined(HIL_POSITION_ENCODER) && !defined(HIL_POSITION_AD2S1210)
#error "hil_config.h selects no position mode"
#endif
#if HIL_N_PHASES < 1 || HIL_N_PHASES > 4
#error "the driver has gates for 1..4 phases"
#endif

#ifdef HIL_POSITION_AD2S1210
#define SRC_MASK (DRV_SRC_SENSE | DRV_SRC_POS)
#else
#define SRC_MASK DRV_SRC_SENSE
#endif

#define PIN_RUN GPIO_PIN_6       /* PD6 */
#define PIN_READY GPIO_PIN_4     /* PD4, EXTI4 */
#define STALL_TRIGGERS 3u        /* triggers in a row that find the previous chain unfinished stop the run */
#define HANG_TRIGGERS 3u         /* triggers in a row that find ctrl_isr still running stop the run */
#define PRIO_CTRL 3u

static const srm_hal_t *hal_;
static const char *setup_err;
static volatile bool running, in_ctrl, ready_stop, stall_stop, hang_stop, unwind_pending;
static volatile uint32_t pending, stalls, hangs, t_trigger;
static jmp_buf ctrl_jmp;              /* the context drv_data_done returns to when a hung ctrl_isr is abandoned */
static const char *volatile stop_reason;
static bool has_cmd;
static uint8_t cmd_mode;
static float cmd_value;

/* statistics, written at the ctrl_isr priority */
static volatile uint32_t w_n, w_exec, w_lat, exec_max, overruns;
static volatile float w_i2[4];

static void hal_set_switches(uint8_t phase, bool upper, bool lower) { pwm_set_switches(phase, upper, lower); }
static void hal_set_pwm(uint8_t phase, float duty, srm_chop_t mode) { pwm_set_duty(phase, duty, mode); }
static uint16_t hal_adc_read(uint8_t channel) { return sense_read(channel); }
static uint32_t hal_micros(void) { return TIM2->CNT; }
static float hal_vbus(void) { return HIL_VBUS_V; }

static uint32_t hal_encoder_count(void)
{
#ifdef HIL_POSITION_ENCODER
    return enc_count();
#else
    return 0;
#endif
}

static void hal_resolver_sincos(int16_t *s, int16_t *c)
{
#ifdef HIL_POSITION_AD2S1210
    rdc_sincos(s, c);
#else
    *s = 0;
    *c = 0;
#endif
}

static void run_pin(bool on) { GPIOD->BSRR = on ? PIN_RUN : (uint32_t)PIN_RUN << 16; }
static bool ready_high(void) { return (GPIOD->IDR & PIN_READY) != 0; }

/* Gates off and the run stopped; any priority. */
static void fault_stop(const char *reason, volatile bool *flag)
{
    pwm_kill();
    running = false;
    run_pin(false);
    *flag = true;
    stop_reason = reason;
}

void drv_delay_cycles(uint32_t n)
{
    const uint32_t t0 = DWT->CYCCNT;
    while (DWT->CYCCNT - t0 < n) {}
}

static uint32_t mask_ctrl(void)
{
    const uint32_t old = __get_BASEPRI();
    __set_BASEPRI(PRIO_CTRL << (8u - __NVIC_PRIO_BITS));
    __ISB();
    return old;
}

static void unmask(uint32_t old) { __set_BASEPRI(old); }

void srm_hal_stm32_init(srm_hal_t *hal)
{
    __HAL_RCC_GPIOD_CLK_ENABLE();
    GPIOD->BSRR = (uint32_t)PIN_RUN << 16;
    GPIO_InitTypeDef g = {0};
    g.Pin = PIN_RUN;
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOD, &g);

    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->LAR = 0xC5ACCE55u;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    __HAL_RCC_DMA1_CLK_ENABLE();
    setup_err = pwm_init(HIL_PWM_HZ, HIL_ISR_HZ);

    /* micros(): TIM2, 32 bits at 1 MHz */
    __HAL_RCC_TIM2_CLK_ENABLE();
    TIM2->PSC = DRV_TIMER_HZ / 1000000u - 1u;
    TIM2->ARR = 0xFFFFFFFFu;
    TIM2->EGR = TIM_EGR_UG;
    TIM2->CR1 = TIM_CR1_CEN;

    /* ctrl_slow(): TIM6 at 1 kHz */
    __HAL_RCC_TIM6_CLK_ENABLE();
    TIM6->PSC = DRV_TIMER_HZ / 1000000u - 1u;
    TIM6->ARR = 999u;
    TIM6->EGR = TIM_EGR_UG;
    TIM6->SR = 0;
    TIM6->DIER = TIM_DIER_UIE;
    TIM6->CR1 = TIM_CR1_CEN;
    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);

    sense_init();
    enc_init();
    rdc_init();

    /* READY: pulled down, so a missing emulator reads "not ready" */
    g.Pin = PIN_READY;
    g.Mode = GPIO_MODE_IT_FALLING;
    g.Pull = GPIO_PULLDOWN;
    HAL_GPIO_Init(GPIOD, &g);
    HAL_NVIC_SetPriority(EXTI4_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(EXTI4_IRQn);

    hal->n_phases = HIL_N_PHASES;
    hal->pwm_hz = HIL_PWM_HZ;
    hal->isr_hz = HIL_ISR_HZ;
    hal->adc_bits = HIL_ADC_BITS;
    hal->adc_amps_per_count = HIL_ADC_AMPS_PER_COUNT;
    hal->adc_offset_counts = HIL_ADC_OFFSET_COUNTS;
#ifdef HIL_POSITION_ENCODER
    hal->encoder_cpr = HIL_ENCODER_CPR;
#else
    hal->encoder_cpr = 0;
#endif
    hal->set_switches = hal_set_switches;
    hal->set_pwm = hal_set_pwm;
    hal->adc_read = hal_adc_read;
    hal->encoder_count = hal_encoder_count;
    hal->resolver_sincos = hal_resolver_sincos;
    hal->micros = hal_micros;
    hal->vbus_volts = hal_vbus;
    hal->adc_volts_per_count = HIL_ADC_VOLTS_PER_COUNT;
    hal->adc_volt_offset_counts = HIL_ADC_VOLT_OFFSET_COUNTS;
    hal_ = hal;
}

const char *drv_start(void)
{
    if (running) return "start refused: running";
    if (setup_err) return setup_err;
    if (!pwm_phase_ok()) return "start refused: the PWM timers do not update at the counter underflow";
    const char *e = sense_check();
    if (e) return e;
    if (!ready_high()) return "start refused: READY is low (start the emulator first)";
    e = rdc_configure();
    if (e) return e;

    /* zeroed compares reach the active registers at the next updates */
    pwm_kill();
    sense_abort();
    rdc_abort();
    drv_delay_cycles((uint32_t)(2.0f * (float)DRV_CPU_HZ / HIL_ISR_HZ));
    if (unwind_pending) return "start refused: the last ctrl_isr has not been abandoned yet";
    pending = 0;
    stalls = hangs = 0;
    in_ctrl = false;
    ready_stop = stall_stop = hang_stop = false;
    stop_reason = NULL;
    const uint32_t m = mask_ctrl();
    w_n = w_exec = w_lat = exec_max = overruns = 0;
    for (int k = 0; k < 4; k++) w_i2[k] = 0.0f;
    unmask(m);
    enc_start();
    ctrl_init(hal_);
    if (has_cmd) ctrl_command(cmd_mode ? SRM_CMD_SPEED : SRM_CMD_TORQUE, cmd_value);
    run_pin(true);
    drv_delay_cycles(DRV_CPU_HZ / 50000u);     /* 20 us: the emulator sees RUN before the first trigger */
    __disable_irq();          /* READY checked and the outputs enabled with no READY interrupt in between */
    if (!ready_high()) {
        __enable_irq();
        run_pin(false);
        return "start refused: READY fell during the start";
    }
    running = true;
    pwm_enable();
    __enable_irq();
    return NULL;
}

void drv_stop(void)
{
    pwm_kill();
    running = false;
    run_pin(false);
}

bool drv_running(void) { return running; }

const char *drv_take_stop_reason(void)
{
    return __atomic_exchange_n(&stop_reason, NULL, __ATOMIC_RELAXED);
}

int drv_param(const char *name, float value)
{
    const uint32_t m = mask_ctrl();
    const int r = ctrl_param(name, value);
    unmask(m);
    return r;
}

void drv_command(uint8_t mode, float value)
{
    const uint32_t m = mask_ctrl();
    has_cmd = true;
    cmd_mode = mode;
    cmd_value = value;
    if (running) ctrl_command(mode ? SRM_CMD_SPEED : SRM_CMD_TORQUE, value);
    unmask(m);
}

void drv_stats(drv_stats_t *s)
{
    const uint32_t m = mask_ctrl();
    const uint32_t n = w_n, ex = w_exec, lat = w_lat;
    float i2[4];
    for (int k = 0; k < 4; k++) {
        i2[k] = w_i2[k];
        w_i2[k] = 0.0f;
    }
    w_n = w_exec = w_lat = 0;
    s->isr_max_us = (float)exec_max * (1e6f / (float)DRV_CPU_HZ);
    s->overruns = overruns;
    unmask(m);
    const float us = 1e6f / (float)DRV_CPU_HZ;
    s->isr_mean_us = n ? (float)ex / (float)n * us : 0.0f;
    s->sample_us = n ? (float)lat / (float)n * us : 0.0f;
    for (int k = 0; k < 4; k++) s->i_rms[k] = n ? sqrtf(i2[k] / (float)n) : 0.0f;
    s->command = cmd_value;
    s->state = (uint8_t)((running ? 1u : 0u) | (ready_high() ? 2u : 0u) | (ready_stop ? 4u : 0u) |
                         (stall_stop ? 8u : 0u) | (enc_index_seen() ? 16u : 0u) | (hang_stop ? 32u : 0u));
}

bool drv_sample_wanted(uint32_t src) { return (pending & src) != 0; }

void drv_data_done(uint32_t src)
{
    const uint32_t old = __atomic_fetch_and(&pending, ~src, __ATOMIC_RELAXED);
    if (!(old & src) || (old & ~src) || !running) return;
    stalls = 0;
    if (setjmp(ctrl_jmp)) {   /* the trigger abandoned a hung ctrl_isr (abandon_ctrl_isr) */
        in_ctrl = false;
        unwind_pending = false;
        return;
    }
    const uint32_t t0 = DWT->CYCCNT;
    in_ctrl = true;
    ctrl_isr();
    const uint32_t exec = DWT->CYCCNT - t0;
    in_ctrl = false;
    w_n++;
    w_exec += exec;
    w_lat += t0 - t_trigger;
    if (exec > exec_max) exec_max = exec;
    for (uint8_t k = 0; k < HIL_N_PHASES; k++) {
        const float i = ((float)sense_read(k) - (float)HIL_ADC_OFFSET_COUNTS) * HIL_ADC_AMPS_PER_COUNT;
        w_i2[k] += i * i;
    }
}

static void unwind_target(void) { longjmp(ctrl_jmp, 1); }

/* ctrl_isr runs in the data interrupt this trigger interrupted when none of the priority 2 interrupts is active in
 * between (they are short: a later trigger finds it on top). */
static bool ctrl_frame_on_top(void)
{
    return !NVIC_GetActive(EXTI3_IRQn) && !NVIC_GetActive(TIM7_IRQn) && !NVIC_GetActive(EXTI15_10_IRQn);
}

/* Abandon a hung ctrl_isr: the interrupted frame (the data interrupt running ctrl_isr) returns into unwind_target,
 * which longjmps back to drv_data_done, so that interrupt ends normally. frame: the exception frame on the MSP. */
static void abandon_ctrl_isr(uint32_t *frame)
{
    frame[6] = (uint32_t)&unwind_target & ~1u;     /* stacked PC (bit 0 clear) */
    frame[7] &= ~0x0600FC00u;                      /* stacked xPSR: clear IT/ICI, the new PC starts no IT block */
}

/* The sample trigger: TIM1 update at the counter underflow. Entered through TIM1_UP_IRQHandler with the frame. */
__attribute__((used)) void trigger_irq(uint32_t *frame)
{
    TIM1->SR = ~TIM_SR_UIF;
    __DSB();
    if (unwind_pending && in_ctrl && ctrl_frame_on_top()) {
        abandon_ctrl_isr(frame);
        return;
    }
    if (!running) return;
    if (!ready_high()) {
        fault_stop("stopped: READY low (emulator stopped or faulted)", &ready_stop);
        return;
    }
    if (in_ctrl) {               /* ctrl_isr still runs: this sample is skipped */
        overruns++;
        if (++hangs >= HANG_TRIGGERS) {
            fault_stop("stopped: ctrl_isr did not return for 3 triggers (abandoned)", &hang_stop);
            unwind_pending = true;
            if (ctrl_frame_on_top()) abandon_ctrl_isr(frame);
        }
        return;
    }
    hangs = 0;
    if (pending) {               /* the previous chain has not finished: restart it */
        overruns++;
        if (++stalls >= STALL_TRIGGERS) {
            fault_stop("stopped: the sample chain stalled (no conversion data for 3 triggers)", &stall_stop);
            return;
        }
        sense_abort();
        rdc_abort();
    }
    t_trigger = DWT->CYCCNT;
    pending = SRC_MASK;
    sense_trigger();
    rdc_trigger();
}

__attribute__((naked)) void TIM1_UP_IRQHandler(void)
{
    __asm volatile("mrs r0, msp\n\tb trigger_irq\n");
}

/* READY falling: gates off within the interrupt latency. */
void EXTI4_IRQHandler(void)
{
    EXTI->PR1 = PIN_READY;
    __DSB();
    if (running) fault_stop("stopped: READY low (emulator stopped or faulted)", &ready_stop);
}

void TIM6_DAC_IRQHandler(void)
{
    TIM6->SR = 0;
    __DSB();
    if (running) ctrl_slow();
}

void dma_clear(DMA_Stream_TypeDef *s)
{
    static const uint8_t shift[4] = {0, 6, 16, 22};
    const uint32_t n = ((uint32_t)s - (uint32_t)DMA1_Stream0) / 0x18u;
    const uint32_t bits = 0x3Du << shift[n & 3u];
    if (n < 4u) DMA1->LIFCR = bits;
    else DMA1->HIFCR = bits;
}

void dma_start(DMA_Stream_TypeDef *s, uint32_t request, volatile void *periph, void *mem, uint32_t n, uint32_t cr)
{
    const uint32_t idx = ((uint32_t)s - (uint32_t)DMA1_Stream0) / 0x18u;
    s->CR &= ~DMA_SxCR_EN;
    while (s->CR & DMA_SxCR_EN) {}
    dma_clear(s);
    (DMAMUX1_Channel0 + idx)->CCR = request;
    s->PAR = (uint32_t)periph;
    s->M0AR = (uint32_t)mem;
    s->NDTR = n;
    s->FCR = 0;
    s->CR = cr;
    s->CR = cr | DMA_SxCR_EN;
}
