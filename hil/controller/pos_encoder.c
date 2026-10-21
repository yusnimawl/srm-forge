/* Quadrature encoder (position = encoder or both): A PD12 (TIM4_CH1, AF2), B PD13 (TIM4_CH2, AF2), Z PG14 (EXTI14,
 * rising), all pulled down.
 *
 * TIM4 counts every A and B edge (encoder mode 3, x4) with ARR = cpr - 1, so it reads the single-turn count the SIL's
 * encoder model gives; it counts up while A leads B (counter-clockwise). No input filter: the index interrupt must
 * see the count that its own edge produced. The index sets the count to 0 (the emulator's Z is high exactly at count
 * 0 mod cpr); until the first index the count is relative to where the timer started. */
#include "srm_hal_stm32.h"

#include "hil_config.h"

#ifdef HIL_POSITION_ENCODER

#define PIN_Z GPIO_PIN_14

static volatile bool index_seen;

void enc_init(void)
{
    __HAL_RCC_GPIOG_CLK_ENABLE();
    __HAL_RCC_TIM4_CLK_ENABLE();
    GPIO_InitTypeDef g = {0};
    g.Pin = GPIO_PIN_12 | GPIO_PIN_13;
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLDOWN;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    g.Alternate = GPIO_AF2_TIM4;
    HAL_GPIO_Init(GPIOD, &g);

    TIM4->CR1 = 0;
    TIM4->SMCR = TIM_SMCR_SMS_1 | TIM_SMCR_SMS_0;                       /* encoder mode 3 */
    TIM4->CCMR1 = (1u << TIM_CCMR1_CC1S_Pos) | (1u << TIM_CCMR1_CC2S_Pos);   /* TI1, TI2, no filter */
    TIM4->CCER = 0;                                                     /* both non-inverted */
    TIM4->PSC = 0;
    TIM4->ARR = HIL_ENCODER_CPR - 1u;
    TIM4->EGR = TIM_EGR_UG;
    TIM4->CNT = 0;
    TIM4->CR1 = TIM_CR1_CEN;

    g.Pin = PIN_Z;
    g.Mode = GPIO_MODE_IT_RISING;
    g.Pull = GPIO_PULLDOWN;
    g.Alternate = 0;
    HAL_GPIO_Init(GPIOG, &g);
    HAL_NVIC_SetPriority(EXTI15_10_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
}

void enc_start(void) { index_seen = false; }
uint32_t enc_count(void) { return TIM4->CNT; }
bool enc_index_seen(void) { return index_seen; }

void EXTI15_10_IRQHandler(void)
{
    if (EXTI->PR1 & PIN_Z) {
        TIM4->CNT = 0;
        EXTI->PR1 = PIN_Z;
        index_seen = true;
        __DSB();
    }
}

#else

void enc_init(void) {}
void enc_start(void) {}
uint32_t enc_count(void) { return 0; }
bool enc_index_seen(void) { return false; }

#endif
