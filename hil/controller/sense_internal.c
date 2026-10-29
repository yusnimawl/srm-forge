/* Current sensing with the MCU's own ADCs (current_sense = internal): DAC outputs into ADC1 + ADC2 in dual regular
 * simultaneous mode, 16 bits.
 *
 * Phase A PA3 (ADC12_INP15, ADC1 rank 1), B PB1 (INP5, ADC2 rank 1), C PC0 (INP10, ADC1 rank 2), D PA4 (INP18, ADC2
 * rank 2). TIM1 TRGO2 (the update at the counter underflow) starts both sequences in hardware; the common data
 * register (ADC1 in bits 15:0, ADC2 in 31:16) goes by circular DMA (DMA1 stream 0, two words per trigger), and its
 * transfer-complete interrupt completes the sample. ADC clock: AHB / 4 = 50 MHz, 8.5 cycles sampling.
 *
 * PA5 and PA6 carry the DAC clock and data from the emulator in this mode: both are inputs (pulled down), and drv_start
 * checks PA5 before RUN goes high. CS (PD14) stays high and CONVST (PD15) low. There are no voltage channels. */
#include "srm_hal_stm32.h"

#include "hil_config.h"

#ifdef HIL_CURRENT_SENSE_INTERNAL

#define STREAM DMA1_Stream0

static ADC_HandleTypeDef adc1, adc2;
static uint32_t rx[8] __attribute__((aligned(32)));     /* DMA target, one cache line */
static uint16_t raw[4];
static const char *init_err;

static void adc_common(ADC_HandleTypeDef *h, ADC_TypeDef *inst, uint32_t trigger, uint32_t data)
{
    h->Instance = inst;
    h->Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
    h->Init.Resolution = ADC_RESOLUTION_16B;
    h->Init.ScanConvMode = ADC_SCAN_ENABLE;
    h->Init.EOCSelection = ADC_EOC_SEQ_CONV;
    h->Init.LowPowerAutoWait = DISABLE;
    h->Init.ContinuousConvMode = DISABLE;
    h->Init.NbrOfConversion = 2;
    h->Init.DiscontinuousConvMode = DISABLE;
    h->Init.ExternalTrigConv = trigger;
    h->Init.ExternalTrigConvEdge = trigger == ADC_SOFTWARE_START ? ADC_EXTERNALTRIGCONVEDGE_NONE
                                                                 : ADC_EXTERNALTRIGCONVEDGE_RISING;
    h->Init.ConversionDataManagement = data;
    h->Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    h->Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
    h->Init.OversamplingMode = DISABLE;
    if (HAL_ADC_Init(h) != HAL_OK) init_err = "setup refused: ADC init";
}

static void channel(ADC_HandleTypeDef *h, uint32_t ch, uint32_t rank)
{
    ADC_ChannelConfTypeDef c = {0};
    c.Channel = ch;
    c.Rank = rank;
    c.SamplingTime = ADC_SAMPLETIME_8CYCLES_5;
    c.SingleDiff = ADC_SINGLE_ENDED;
    c.OffsetNumber = ADC_OFFSET_NONE;
    if (HAL_ADC_ConfigChannel(h, &c) != HAL_OK) init_err = "setup refused: ADC channel";
}

void sense_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    GPIOD->BSRR = GPIO_PIN_14 | ((uint32_t)GPIO_PIN_15 << 16);
    GPIO_InitTypeDef g = {0};
    g.Pin = GPIO_PIN_14 | GPIO_PIN_15;
    g.Mode = GPIO_MODE_OUTPUT_PP;
    HAL_GPIO_Init(GPIOD, &g);
    g.Pin = GPIO_PIN_5 | GPIO_PIN_6;
    g.Mode = GPIO_MODE_INPUT;
    g.Pull = GPIO_PULLDOWN;
    HAL_GPIO_Init(GPIOA, &g);
    g.Mode = GPIO_MODE_ANALOG;
    g.Pull = GPIO_NOPULL;
    g.Pin = GPIO_PIN_3 | GPIO_PIN_4;
    HAL_GPIO_Init(GPIOA, &g);
    g.Pin = GPIO_PIN_1;
    HAL_GPIO_Init(GPIOB, &g);
    g.Pin = GPIO_PIN_0;
    HAL_GPIO_Init(GPIOC, &g);

    __HAL_RCC_ADC12_CLK_ENABLE();
    adc_common(&adc1, ADC1, ADC_EXTERNALTRIG_T1_TRGO2, ADC_CONVERSIONDATA_DMA_CIRCULAR);
    adc_common(&adc2, ADC2, ADC_SOFTWARE_START, ADC_CONVERSIONDATA_DR);
    /* calibrated before the dual mode is set: afterwards the ADC2 calibration never finished (measured) */
    if (HAL_ADCEx_Calibration_Start(&adc1, ADC_CALIB_OFFSET_LINEARITY, ADC_SINGLE_ENDED) != HAL_OK ||
        HAL_ADCEx_Calibration_Start(&adc2, ADC_CALIB_OFFSET_LINEARITY, ADC_SINGLE_ENDED) != HAL_OK)
        init_err = "setup refused: ADC calibration";
    ADC_MultiModeTypeDef mm = {0};
    mm.Mode = ADC_DUALMODE_REGSIMULT;
    mm.DualModeData = ADC_DUALMODEDATAFORMAT_32_10_BITS;
    mm.TwoSamplingDelay = ADC_TWOSAMPLINGDELAY_1CYCLE;
    if (HAL_ADCEx_MultiModeConfigChannel(&adc1, &mm) != HAL_OK) init_err = "setup refused: ADC dual mode";
    channel(&adc1, ADC_CHANNEL_15, ADC_REGULAR_RANK_1);
    channel(&adc1, ADC_CHANNEL_10, ADC_REGULAR_RANK_2);
    channel(&adc2, ADC_CHANNEL_5, ADC_REGULAR_RANK_1);
    channel(&adc2, ADC_CHANNEL_18, ADC_REGULAR_RANK_2);
    if (init_err) return;
    if (ADC_Enable(&adc1) != HAL_OK || ADC_Enable(&adc2) != HAL_OK) {
        init_err = "setup refused: ADC enable";
        return;
    }
    ADC1->ISR = ADC_ISR_EOC | ADC_ISR_EOS | ADC_ISR_OVR;
    HAL_NVIC_SetPriority(DMA1_Stream0_IRQn, 3, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream0_IRQn);
    dma_start(STREAM, DMA_REQUEST_ADC1, &ADC12_COMMON->CDR, rx, 2,
              DMA_SxCR_PL_1 | DMA_SxCR_MSIZE_1 | DMA_SxCR_PSIZE_1 | DMA_SxCR_MINC | DMA_SxCR_CIRC | DMA_SxCR_TCIE);
    ADC1->CR |= ADC_CR_ADSTART;
}

const char *sense_check(void)
{
    if (init_err) return init_err;
    if ((GPIOA->MODER >> (5u * 2u)) & 3u) return "start refused: PA5 is not an input";
    return NULL;
}

void sense_trigger(void) {}
void sense_abort(void) {}

void DMA1_Stream0_IRQHandler(void)
{
    dma_clear(STREAM);
    __DSB();
    SCB_InvalidateDCache_by_Addr(rx, sizeof rx);
    raw[0] = (uint16_t)rx[0];
    raw[1] = (uint16_t)(rx[0] >> 16);
    raw[2] = (uint16_t)rx[1];
    raw[3] = (uint16_t)(rx[1] >> 16);
    drv_data_done(DRV_SRC_SENSE);
}

uint16_t sense_read(uint8_t channel) { return channel < HIL_N_PHASES ? raw[channel] : 0; }

#endif
