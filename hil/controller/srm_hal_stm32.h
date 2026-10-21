/* NUCLEO-H723ZG driver behind srm_hal_t: the owner's controller C runs unchanged on it.
 *
 * Sample chain, once per ISR period (isr_hz):
 *   TIM1 update at the counter underflow (the centre of the on-pulses, where the SIL samples)
 *     -> ad7606:   CONVST pulse (PD15) -> BUSY falls (EXTI3, PF3) -> SPI1 DMA read of V1..V8 (CS PD14)
 *        internal: TRGO2 starts ADC1 + ADC2 (dual simultaneous, DMA) in hardware
 *     -> ad2s1210: SAMPLE pulse (PG2) and, HIL_RDC_READ_DELAY_US later (TIM7), an SPI3 DMA read of the position
 *     -> when every source of the build has its data: ctrl_isr()
 * The compare values written by ctrl_isr are preloaded and take effect at the next update, one ISR period after the
 * sample, as the SIL's default compute delay.
 *
 * Interrupt priorities (lower is more urgent): 0 READY falling (gates off), 1 TIM1 update (trigger), 2 BUSY, TIM7,
 * encoder index, 3 the data DMA streams (ctrl_isr runs here), 5 TIM6 (ctrl_slow, 1 kHz), 15 SysTick. The serial link
 * and ctrl_param / ctrl_command run in the main loop; ctrl_param and ctrl_command run with priority 3 and below
 * masked, so they never interleave with ctrl_isr.
 *
 * Safety: the gate outputs idle low (TIM1/TIM8 MOE = 0, OSSI = 1) except while running. RUN (PD6) goes high only
 * after drv_start's checks; READY (PD4) falling, or READY found low at a trigger, turns every gate off at once (MOE
 * cleared, every compare 0) and stops the run. Two triggers in a row with the previous sample chain unfinished stop
 * the run as well ("stall"). */
#ifndef SRM_HAL_STM32_H
#define SRM_HAL_STM32_H

#include <stdbool.h>
#include <stdint.h>

#include "srm_hal.h"
#include "stm32h7xx_hal.h"

#ifndef HIL_RDC_READ_DELAY_US
#define HIL_RDC_READ_DELAY_US 2u      /* SAMPLE to the start of the position read (the emulator latches in software) */
#endif
#ifndef HIL_SPI_MBR
#define HIL_SPI_MBR 3u                /* SPI1/SPI3 clock = 200 MHz kernel clock / 2^(MBR+1): 3 = 12.5 MHz */
#endif

#define DRV_TIMER_HZ 200000000u       /* TIM1/TIM8 (APB2) and TIM2/TIM6/TIM7 (APB1) kernel clocks */
#define DRV_CPU_HZ 400000000u

/* Fill every srm_hal_t field from hil_config.h and set up the peripherals; gates stay off and RUN low. A setup that
 * cannot run (rates out of range) is reported by drv_start. */
void srm_hal_stm32_init(srm_hal_t *hal);

/* Start a run: checks (setup, PA5 an input in internal mode, the AD2S1210 configuration, READY high), ctrl_init, the
 * last command, outputs on, RUN high. Returns NULL or the reason it refused. */
const char *drv_start(void);
void drv_stop(void);
bool drv_running(void);
/* A reason the last run stopped by itself (READY low, stall), once; NULL when none is new. */
const char *drv_take_stop_reason(void);

/* ctrl_param / ctrl_command with the ctrl_isr priority masked; the command is kept and re-applied after ctrl_init. */
int drv_param(const char *name, float value);
void drv_command(uint8_t mode, float value);

typedef struct {
    float isr_mean_us, isr_max_us, sample_us, command;
    float i_rms[4];
    uint32_t overruns;
    uint8_t state;
} drv_stats_t;
/* Statistics of the window since the last call (maximum and overruns since the start). */
void drv_stats(drv_stats_t *s);

/* ---- between the driver's own files ---- */

/* Sample sources; drv_data_done(bit) from each source's completion interrupt (priority 3). */
#define DRV_SRC_SENSE 1u
#define DRV_SRC_POS 2u
void drv_data_done(uint32_t src);
bool drv_sample_wanted(uint32_t src);    /* the current trigger still waits for this source */

/* pwm_ahb.c: TIM1 (upper) master and TIM8 (lower) slave. */
const char *pwm_init(float pwm_hz, float isr_hz);   /* NULL or the reason the rates cannot be set */
uint16_t pwm_arr(void);
void pwm_set_switches(uint8_t phase, bool upper, bool lower);
void pwm_set_duty(uint8_t phase, float duty, srm_chop_t mode);
void pwm_kill(void);               /* outputs to idle low now, every compare 0 */
void pwm_enable(void);             /* outputs follow the compares (MOE = 1) */
bool pwm_phase_ok(void);           /* both timers update at the underflow */

/* sense_ad7606.c / sense_internal.c: the build's current sensing. */
void sense_init(void);
void sense_trigger(void);          /* TIM1 update interrupt */
void sense_abort(void);
const char *sense_check(void);
uint16_t sense_read(uint8_t channel);

/* pos_encoder.c / pos_ad2s1210.c: position sources (each a no-op outside its mode). */
void enc_init(void);
void enc_start(void);
uint32_t enc_count(void);
bool enc_index_seen(void);
void rdc_init(void);
const char *rdc_configure(void);   /* at start: resolution written and read back */
void rdc_trigger(void);            /* TIM1 update interrupt */
void rdc_abort(void);
void rdc_sincos(int16_t *s, int16_t *c);

/* link.c: the serial link (USART3, ST-LINK virtual COM port). */
void link_init(void);
void link_poll(void);

/* DMA1 stream helpers (streams 0..4; stream n uses DMAMUX1 channel n). */
void dma_clear(DMA_Stream_TypeDef *s);
void dma_start(DMA_Stream_TypeDef *s, uint32_t request, volatile void *periph, void *mem, uint32_t n, uint32_t cr);
/* Busy-wait n CPU cycles on the cycle counter. */
void drv_delay_cycles(uint32_t n);

#endif
