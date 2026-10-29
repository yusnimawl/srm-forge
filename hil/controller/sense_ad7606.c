/* Current and voltage sensing with an AD7606 (current_sense = ad7606), serial interface on SPI1.
 *
 * Pins: CONVST PD15 (out, idle low), BUSY PF3 (in, EXTI3 falling, pulled down), CS PD14 (out, idle high), SCLK PA5
 * (SPI1_SCK, AF5), DOUTA PA6 (SPI1_MISO, AF5, pulled down: the emulator tri-states it while CS is high). MOSI is not
 * wired.
 *
 * The trigger raises CONVST for 150 ns (the conversion starts on the rising edge); BUSY falling starts one 128-bit
 * read, V1..V8 as 16-bit two's complement MSB first, in SPI mode 2 (CPOL 1, CPHA 0: DB15 is out when CS falls and is
 * sampled on the first, falling, SCK edge). SPI1 is a receive-only master (TSIZE 8 frames of 16 bits) whose RX DMA
 * (DMA1 stream 1) completes the sample. V1..V4 are the phase currents, V5..V8 the phase voltages; the controller gets
 * them as offset binary (code + 32768). */
#include "srm_hal_stm32.h"

#include "hil_config.h"

#ifdef HIL_CURRENT_SENSE_AD7606

#include "hil_chips.h"

#define PIN_CS GPIO_PIN_14       /* PD14 */
#define PIN_CONVST GPIO_PIN_15   /* PD15 */
#define PIN_BUSY GPIO_PIN_3      /* PF3 */
#define N_CH 8u
#define PULSE_CYCLES 60u         /* 150 ns */
#define CS_SETUP_CYCLES 40u      /* 100 ns from CS falling to the first SCK edge */
#define STREAM DMA1_Stream1

static uint16_t rx[16] __attribute__((aligned(32)));    /* DMA target, one cache line */
static int16_t raw[N_CH];
static volatile bool reading;

#define CFG2_RX (SPI_CFG2_AFCNTR | SPI_CFG2_SSM | SPI_CFG2_CPOL | SPI_CFG2_MASTER | (2u << SPI_CFG2_COMM_Pos))

void sense_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOF_CLK_ENABLE();
    __HAL_RCC_SPI1_CLK_ENABLE();
    GPIOD->BSRR = PIN_CS | ((uint32_t)PIN_CONVST << 16);
    GPIO_InitTypeDef g = {0};
    g.Pin = PIN_CS | PIN_CONVST;
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    HAL_GPIO_Init(GPIOD, &g);

    SPI1->CR1 = SPI_CR1_SSI;     /* internal SS high before MASTER is set, else a mode fault clears MASTER */
    SPI1->CFG1 = (HIL_SPI_MBR << SPI_CFG1_MBR_Pos) | SPI_CFG1_RXDMAEN | (15u << SPI_CFG1_DSIZE_Pos);
    SPI1->CFG2 = CFG2_RX;
    g.Pin = GPIO_PIN_5 | GPIO_PIN_6;
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLDOWN;
    g.Alternate = GPIO_AF5_SPI1;
    HAL_GPIO_Init(GPIOA, &g);

    g.Pin = PIN_BUSY;
    g.Mode = GPIO_MODE_IT_FALLING;
    g.Pull = GPIO_PULLDOWN;
    g.Alternate = 0;
    HAL_GPIO_Init(GPIOF, &g);
    HAL_NVIC_SetPriority(EXTI3_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(EXTI3_IRQn);
    HAL_NVIC_SetPriority(DMA1_Stream1_IRQn, 3, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream1_IRQn);
}

const char *sense_check(void) { return NULL; }

void sense_trigger(void)
{
    GPIOD->BSRR = PIN_CONVST;
    drv_delay_cycles(PULSE_CYCLES);
    GPIOD->BSRR = (uint32_t)PIN_CONVST << 16;
}

static void spi_end(void)
{
    GPIOD->BSRR = PIN_CS;
    SPI1->IFCR = SPI_IFCR_EOTC | SPI_IFCR_TXTFC | SPI_IFCR_OVRC | SPI_IFCR_MODFC | SPI_IFCR_SUSPC;
    SPI1->CR1 = SPI_CR1_SSI;
    reading = false;
}

void sense_abort(void)
{
    STREAM->CR &= ~DMA_SxCR_EN;
    if (SPI1->CR1 & SPI_CR1_CSTART) {
        SPI1->CR1 |= SPI_CR1_CSUSP;
        const uint32_t t0 = DWT->CYCCNT;
        while (!(SPI1->SR & SPI_SR_SUSP) && DWT->CYCCNT - t0 < 4000u) {}
    }
    while (STREAM->CR & DMA_SxCR_EN) {}
    dma_clear(STREAM);
    spi_end();
}

/* BUSY falling: the conversion is in; read it. */
void EXTI3_IRQHandler(void)
{
    EXTI->PR1 = PIN_BUSY;
    __DSB();
    if (reading || !drv_sample_wanted(DRV_SRC_SENSE)) return;
    reading = true;
    dma_start(STREAM, DMA_REQUEST_SPI1_RX, &SPI1->RXDR, rx, N_CH,
              DMA_SxCR_PL_1 | DMA_SxCR_MSIZE_0 | DMA_SxCR_PSIZE_0 | DMA_SxCR_MINC | DMA_SxCR_TCIE);
    SPI1->CR2 = N_CH;
    GPIOD->BSRR = (uint32_t)PIN_CS << 16;
    SPI1->CR1 = SPI_CR1_SSI | SPI_CR1_SPE;
    drv_delay_cycles(CS_SETUP_CYCLES);
    SPI1->CR1 = SPI_CR1_SSI | SPI_CR1_SPE | SPI_CR1_CSTART;
}

void DMA1_Stream1_IRQHandler(void)
{
    dma_clear(STREAM);
    __DSB();
    spi_end();
    SCB_InvalidateDCache_by_Addr(rx, sizeof rx);
    for (unsigned j = 0; j < N_CH; j++) raw[j] = (int16_t)rx[j];
    drv_data_done(DRV_SRC_SENSE);
}

uint16_t sense_read(uint8_t channel)
{
    if (channel < HIL_N_PHASES) return ad7606_to_unsigned(raw[channel]);
    if (channel < 2 * HIL_N_PHASES) return ad7606_to_unsigned(raw[4 + channel - HIL_N_PHASES]);
    return 0;
}

#endif
