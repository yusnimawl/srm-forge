/* AD2S1210 resolver-to-digital converter (position = ad2s1210 or both) on SPI3.
 *
 * Pins: SCLK PC10, MISO PC11 (pulled down), MOSI PC12 (SPI3, AF6), WR/FSYNC PD2 (out, idle high), SAMPLE PG2 (out,
 * idle high), A0 PG3 and A1 PD7 (out; 0/0 selects the position register).
 *
 * At start the control register (0x92) gets the resolution of hil_config.h (HIL_RDC_BITS, RES and EnRES) and is read
 * back; configuration mode (A0 = A1 = 1) uses 8-bit frames, one per WR/FSYNC cycle, at least 1 us apart. Each trigger
 * pulls SAMPLE low for 150 ns (the falling edge latches position and velocity); HIL_RDC_READ_DELAY_US later (TIM7, one
 * pulse) SPI3 reads the 24-bit normal-mode frame (the 16-bit position word, MSB-aligned at the resolution, then the
 * fault register) by DMA (DMA1 stream 2), in SPI mode 3 (CPOL 1, CPHA 1), receive only. resolver_sincos gives
 * round(32767 sin/cos) of that electrical angle. */
#include "srm_hal_stm32.h"

#include "hil_config.h"

#ifdef HIL_POSITION_AD2S1210

#include <math.h>
#include <stdio.h>

#include "hil_chips.h"

#define PIN_FSYNC GPIO_PIN_2     /* PD2 */
#define PIN_A1 GPIO_PIN_7        /* PD7 */
#define PIN_SAMPLE GPIO_PIN_2    /* PG2 */
#define PIN_A0 GPIO_PIN_3        /* PG3 */
#define REG_CONTROL 0x92u
#define PULSE_CYCLES 60u         /* 150 ns */
#define CS_SETUP_CYCLES 40u
#define GAP_CYCLES (DRV_CPU_HZ / 500000u)    /* 2 us between configuration frames */
#define STREAM DMA1_Stream2
#define CFG2_BASE (SPI_CFG2_AFCNTR | SPI_CFG2_SSM | SPI_CFG2_CPOL | SPI_CFG2_CPHA | SPI_CFG2_MASTER)

#if HIL_RDC_BITS != 10 && HIL_RDC_BITS != 12 && HIL_RDC_BITS != 14 && HIL_RDC_BITS != 16
#error "HIL_RDC_BITS must be 10, 12, 14 or 16"
#endif

static uint8_t rx[32] __attribute__((aligned(32)));      /* DMA target, one cache line */
static volatile uint16_t word;
static uint16_t cached_word;
static bool cached_valid;
static int16_t cached_s, cached_c;
static volatile bool reading;
static char err[96];

void rdc_init(void)
{
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOG_CLK_ENABLE();
    __HAL_RCC_SPI3_CLK_ENABLE();
    __HAL_RCC_TIM7_CLK_ENABLE();
    GPIOD->BSRR = PIN_FSYNC | ((uint32_t)PIN_A1 << 16);
    GPIOG->BSRR = PIN_SAMPLE | ((uint32_t)PIN_A0 << 16);
    GPIO_InitTypeDef g = {0};
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    g.Pin = PIN_FSYNC | PIN_A1;
    HAL_GPIO_Init(GPIOD, &g);
    g.Pin = PIN_SAMPLE | PIN_A0;
    HAL_GPIO_Init(GPIOG, &g);

    SPI3->CR1 = SPI_CR1_SSI;     /* internal SS high before MASTER is set, else a mode fault clears MASTER */
    SPI3->CFG1 = (HIL_SPI_MBR << SPI_CFG1_MBR_Pos) | (7u << SPI_CFG1_DSIZE_Pos);
    SPI3->CFG2 = CFG2_BASE | (2u << SPI_CFG2_COMM_Pos);
    g.Pin = GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12;
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLDOWN;
    g.Alternate = GPIO_AF6_SPI3;
    HAL_GPIO_Init(GPIOC, &g);

    TIM7->CR1 = 0;
    TIM7->PSC = 0;
    TIM7->ARR = HIL_RDC_READ_DELAY_US * (DRV_TIMER_HZ / 1000000u) - 1u;
    TIM7->SR = 0;
    TIM7->DIER = TIM_DIER_UIE;
    HAL_NVIC_SetPriority(TIM7_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(TIM7_IRQn);
    HAL_NVIC_SetPriority(DMA1_Stream2_IRQn, 3, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream2_IRQn);
}

static void spi_end(void)
{
    GPIOD->BSRR = PIN_FSYNC;
    SPI3->IFCR = SPI_IFCR_EOTC | SPI_IFCR_TXTFC | SPI_IFCR_OVRC | SPI_IFCR_MODFC | SPI_IFCR_SUSPC;
    SPI3->CR1 = SPI_CR1_SSI;
}

/* One full-duplex 8-bit configuration frame, polled; -1 on a timeout. */
static int xfer8(uint8_t b)
{
    SPI3->CR1 = SPI_CR1_SSI;
    SPI3->CFG1 &= ~SPI_CFG1_RXDMAEN;
    SPI3->CFG2 = CFG2_BASE;
    SPI3->CR2 = 1;
    SPI3->CR1 = SPI_CR1_SSI | SPI_CR1_SPE;
    *(volatile uint8_t *)&SPI3->TXDR = b;
    GPIOD->BSRR = (uint32_t)PIN_FSYNC << 16;
    drv_delay_cycles(CS_SETUP_CYCLES);
    SPI3->CR1 = SPI_CR1_SSI | SPI_CR1_SPE | SPI_CR1_CSTART;
    const uint32_t t0 = DWT->CYCCNT;
    while (!(SPI3->SR & SPI_SR_EOT))
        if (DWT->CYCCNT - t0 > DRV_CPU_HZ / 10000u) {     /* 100 us */
            spi_end();
            return -1;
        }
    const int r = (SPI3->SR & SPI_SR_RXP) ? *(volatile uint8_t *)&SPI3->RXDR : -1;
    spi_end();
    drv_delay_cycles(GAP_CYCLES);
    return r;
}

const char *rdc_configure(void)
{
    const uint8_t code = (uint8_t)((HIL_RDC_BITS - 10) / 2);
    const uint8_t ctrl = (uint8_t)(0x70u | (uint32_t)code << 2 | code);
    GPIOG->BSRR = PIN_A0;
    GPIOD->BSRR = PIN_A1;
    drv_delay_cycles(GAP_CYCLES);
    xfer8(REG_CONTROL);
    xfer8(ctrl);
    xfer8(REG_CONTROL);
    const int back = xfer8(REG_CONTROL);
    GPIOG->BSRR = (uint32_t)PIN_A0 << 16;
    GPIOD->BSRR = (uint32_t)PIN_A1 << 16;
    drv_delay_cycles(GAP_CYCLES);
    SPI3->CFG2 = CFG2_BASE | (2u << SPI_CFG2_COMM_Pos);
    SPI3->CFG1 |= SPI_CFG1_RXDMAEN;
    if (back != ctrl) {
        snprintf(err, sizeof err, "start refused: AD2S1210 control register reads %d, wrote 0x%02x (is it wired?)",
                 back, ctrl);
        return err;
    }
    return NULL;
}

void rdc_trigger(void)
{
    GPIOG->BSRR = (uint32_t)PIN_SAMPLE << 16;
    drv_delay_cycles(PULSE_CYCLES);
    GPIOG->BSRR = PIN_SAMPLE;
    TIM7->CNT = 0;
    TIM7->CR1 = TIM_CR1_OPM | TIM_CR1_URS | TIM_CR1_CEN;
}

void rdc_abort(void)
{
    TIM7->CR1 = 0;
    TIM7->SR = 0;
    STREAM->CR &= ~DMA_SxCR_EN;
    if (SPI3->CR1 & SPI_CR1_CSTART) {
        SPI3->CR1 |= SPI_CR1_CSUSP;
        const uint32_t t0 = DWT->CYCCNT;
        while (!(SPI3->SR & SPI_SR_SUSP) && DWT->CYCCNT - t0 < 4000u) {}
    }
    while (STREAM->CR & DMA_SxCR_EN) {}
    dma_clear(STREAM);
    spi_end();
    reading = false;
}

/* HIL_RDC_READ_DELAY_US after SAMPLE: read the position. */
void TIM7_IRQHandler(void)
{
    TIM7->SR = 0;
    __DSB();
    if (reading || !drv_sample_wanted(DRV_SRC_POS)) return;
    reading = true;
    dma_start(STREAM, DMA_REQUEST_SPI3_RX, &SPI3->RXDR, rx, 3u, DMA_SxCR_PL_1 | DMA_SxCR_MINC | DMA_SxCR_TCIE);
    SPI3->CR2 = 3u;
    GPIOD->BSRR = (uint32_t)PIN_FSYNC << 16;
    SPI3->CR1 = SPI_CR1_SSI | SPI_CR1_SPE;
    drv_delay_cycles(CS_SETUP_CYCLES);
    SPI3->CR1 = SPI_CR1_SSI | SPI_CR1_SPE | SPI_CR1_CSTART;
}

void DMA1_Stream2_IRQHandler(void)
{
    dma_clear(STREAM);
    __DSB();
    spi_end();
    reading = false;
    SCB_InvalidateDCache_by_Addr(rx, sizeof rx);
    word = (uint16_t)((uint16_t)rx[0] << 8 | rx[1]);
    drv_data_done(DRV_SRC_POS);
}

void rdc_sincos(int16_t *s, int16_t *c)
{
    const uint16_t w = word;
    if (!cached_valid || w != cached_word) {
        const float a = (float)ad2s1210_angle(w, HIL_RDC_BITS);
        cached_s = (int16_t)lroundf(32767.0f * sinf(a));
        cached_c = (int16_t)lroundf(32767.0f * cosf(a));
        cached_word = w;
        cached_valid = true;
    }
    *s = cached_s;
    *c = cached_c;
}

#else

void rdc_init(void) {}
const char *rdc_configure(void) { return NULL; }
void rdc_trigger(void) {}
void rdc_abort(void) {}
void rdc_sincos(int16_t *s, int16_t *c)
{
    *s = 0;
    *c = 0;
}

#endif
