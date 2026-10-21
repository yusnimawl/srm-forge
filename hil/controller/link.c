/* PC link on USART3 (PD8 TX / PD9 RX, the ST-LINK virtual COM port), 921600 baud, framed as hil_proto.h, both
 * directions by DMA (RX: DMA1 stream 3, circular; TX: DMA1 stream 4), polled from the main loop.
 *
 * Requests: HELLO -> BUILD_INFO; PARAM_SET -> ctrl_param -> PARAM_REPLY with its status; COMMAND (mode 0 torque N*m,
 * 1 speed rad/s) -> ctrl_command; START, STOP. COMMAND, START and STOP are acknowledged with an empty frame of the same
 * type and sequence number; a refused request gets HIL_ERROR with a text and the request's sequence number. LIVE_CTRL
 * goes out every 50 ms, and HIL_ERROR with the reason when a run stops by itself. */
#include <math.h>
#include <string.h>

#include "srm_hal_stm32.h"
#include "hil_config.h"
#include "hil_hello.h"

#define RX_SIZE 256u
#define TXQ_SIZE 2048u
#define LIVE_MS 50u

static UART_HandleTypeDef uart;
static uint8_t rx_dma[RX_SIZE] __attribute__((aligned(32)));
static uint8_t tx_dma[TXQ_SIZE] __attribute__((aligned(32)));
static uint8_t txq[TXQ_SIZE];
static uint32_t txq_n, rx_tail, tx_dropped;
static uint8_t acc[HIL_FRAME_MAX(HIL_PAYLOAD_MAX)];
static uint32_t acc_n;
static bool acc_over;
static uint8_t frame[HIL_FRAME_MAX(HIL_PAYLOAD_MAX)];
static uint16_t seq_out;

static void send(uint8_t type, uint16_t seq, const void *p, size_t n)
{
    const size_t m = hil_frame(type, seq, p, n, frame);
    if (m == 0 || txq_n + m > TXQ_SIZE) {
        tx_dropped++;
        return;
    }
    memcpy(txq + txq_n, frame, m);
    txq_n += (uint32_t)m;
}

static void reply(uint8_t type, uint16_t seq, const char *err)
{
    if (err) send(HIL_ERROR, seq, err, strlen(err));
    else send(type, seq, NULL, 0);
}

static void tx_pump(void)
{
    if (txq_n == 0 || (DMA1_Stream4->CR & DMA_SxCR_EN)) return;
    const uint32_t n = txq_n;
    memcpy(tx_dma, txq, n);
    txq_n = 0;
    SCB_CleanDCache_by_Addr((uint32_t *)tx_dma, (int32_t)((n + 31u) & ~31u));
    USART3->ICR = USART_ICR_TCCF;
    dma_start(DMA1_Stream4, DMA_REQUEST_USART3_TX, &USART3->TDR, tx_dma, n,
              DMA_SxCR_TRBUFF | DMA_SxCR_PL_0 | DMA_SxCR_MINC | DMA_SxCR_DIR_0);
}

static void dispatch(uint8_t type, uint16_t seq, const uint8_t *p, long len)
{
    const size_t want = hil_payload_size(type);
    if (want && (size_t)len != want) {
        reply(type, seq, "bad payload size");
        return;
    }
    switch (type) {
    case HIL_HELLO: {
        const hil_build_info_t info = {HIL_PROTOCOL_VERSION, 2, HIL_CS_CODE, HIL_POS_CODE, HIL_DAC_CODE,
                                       HIL_FIRMWARE_HASH};
        send(HIL_BUILD_INFO, seq, &info, sizeof info);
        break;
    }
    case HIL_PARAM_SET: {
        hil_param_set_t s;
        memcpy(&s, p, sizeof s);
        if (!memchr(s.name, 0, sizeof s.name) || s.name[0] == 0) {
            reply(type, seq, "parameter refused: name must be 1..23 bytes");
            break;
        }
        if (!isfinite(s.value)) {
            reply(type, seq, "parameter refused: value must be finite");
            break;
        }
        hil_param_reply_t r;
        memcpy(r.name, s.name, sizeof r.name);
        r.status = (int8_t)drv_param(s.name, s.value);
        send(HIL_PARAM_REPLY, seq, &r, sizeof r);
        break;
    }
    case HIL_COMMAND: {
        hil_command_t c;
        memcpy(&c, p, sizeof c);
        if (c.mode > 1 || !isfinite(c.value)) {
            reply(type, seq, "command refused: mode must be 0 (torque) or 1 (speed) with a finite value");
            break;
        }
        drv_command(c.mode, c.value);
        reply(type, seq, NULL);
        break;
    }
    case HIL_START: reply(type, seq, drv_start()); break;
    case HIL_STOP:
        drv_stop();
        reply(type, seq, NULL);
        break;
    default: reply(type, seq, "unknown request");
    }
}

static void feed(uint8_t b)
{
    static uint8_t payload[HIL_PAYLOAD_MAX];
    if (b != 0) {
        if (acc_n < sizeof acc) acc[acc_n++] = b;
        else acc_over = true;
        return;
    }
    uint8_t type = 0;
    uint16_t seq = 0;
    const long len = (acc_n && !acc_over) ? hil_unframe(acc, acc_n, &type, &seq, payload, sizeof payload) : -1;
    acc_n = 0;
    acc_over = false;
    if (len >= 0) dispatch(type, seq, payload, len);
}

void link_init(void)
{
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_USART3_CLK_ENABLE();
    GPIO_InitTypeDef g = {0};
    g.Pin = GPIO_PIN_8 | GPIO_PIN_9;
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLUP;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    g.Alternate = GPIO_AF7_USART3;
    HAL_GPIO_Init(GPIOD, &g);
    uart.Instance = USART3;
    uart.Init.BaudRate = 921600;
    uart.Init.WordLength = UART_WORDLENGTH_8B;
    uart.Init.StopBits = UART_STOPBITS_1;
    uart.Init.Parity = UART_PARITY_NONE;
    uart.Init.Mode = UART_MODE_TX_RX;
    uart.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    uart.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&uart) != HAL_OK) for (;;) {}
    USART3->CR1 &= ~USART_CR1_UE;
    USART3->CR3 |= USART_CR3_OVRDIS | USART_CR3_DMAR | USART_CR3_DMAT;
    USART3->CR1 |= USART_CR1_UE;
    dma_start(DMA1_Stream3, DMA_REQUEST_USART3_RX, &USART3->RDR, rx_dma, RX_SIZE,
              DMA_SxCR_TRBUFF | DMA_SxCR_PL_0 | DMA_SxCR_MINC | DMA_SxCR_CIRC);
}

void link_poll(void)
{
    const uint32_t head = (RX_SIZE - DMA1_Stream3->NDTR) & (RX_SIZE - 1u);
    if (head != rx_tail) {
        SCB_InvalidateDCache_by_Addr((uint32_t *)rx_dma, (int32_t)sizeof rx_dma);
        while (rx_tail != head) {
            feed(rx_dma[rx_tail]);
            rx_tail = (rx_tail + 1u) & (RX_SIZE - 1u);
        }
    }

    const char *why = drv_take_stop_reason();
    if (why) send(HIL_ERROR, seq_out++, why, strlen(why));

    static uint32_t live_ms;
    const uint32_t now = HAL_GetTick();
    if (now - live_ms >= LIVE_MS) {
        live_ms = now;
        drv_stats_t s;
        drv_stats(&s);
        hil_live_ctrl_t l;
        l.isr_mean_us = s.isr_mean_us;
        l.isr_max_us = s.isr_max_us;
        l.isr_overruns = s.overruns;
        l.command = s.command;
        for (int k = 0; k < 4; k++) l.i_meas[k] = s.i_rms[k];
        l.sample_us = s.sample_us;
        l.state = s.state;
        send(HIL_LIVE_CTRL, seq_out++, &l, sizeof l);
    }
    tx_pump();
}
