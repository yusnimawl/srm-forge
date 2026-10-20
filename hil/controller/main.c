/* Nucleo-H723ZG controller. Answers HIL_HELLO over USART3 (ST-LINK virtual COM port, PD8 TX / PD9 RX) at 921600 baud. */
#include "stm32h7xx_hal.h"
#include "hil_hello.h"

static hil_hello_t link_state;
static UART_HandleTypeDef huart3;

void SysTick_Handler(void) { HAL_IncTick(); }

/* 8 MHz bypass clock from the ST-LINK -> PLL1 400 MHz core, 200 MHz AHB, 100 MHz APB. */
static void clock_init(void) {
    HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);
    while (!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {}
    RCC_OscInitTypeDef osc = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = RCC_HSE_BYPASS;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLM = 1;
    osc.PLL.PLLN = 100;
    osc.PLL.PLLP = 2;
    osc.PLL.PLLQ = 4;
    osc.PLL.PLLR = 2;
    osc.PLL.PLLRGE = RCC_PLL1VCIRANGE_3;
    osc.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
    osc.PLL.PLLFRACN = 0;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) for (;;) {}
    RCC_ClkInitTypeDef clk = {0};
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_D1PCLK1 | RCC_CLOCKTYPE_PCLK1 |
                    RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_D3PCLK1;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.SYSCLKDivider = RCC_SYSCLK_DIV1;
    clk.AHBCLKDivider = RCC_HCLK_DIV2;
    clk.APB3CLKDivider = RCC_APB3_DIV2;
    clk.APB1CLKDivider = RCC_APB1_DIV2;
    clk.APB2CLKDivider = RCC_APB2_DIV2;
    clk.APB4CLKDivider = RCC_APB4_DIV2;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2) != HAL_OK) for (;;) {}
}

static void uart_init(void) {
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_USART3_CLK_ENABLE();
    GPIO_InitTypeDef g = {0};
    g.Pin = GPIO_PIN_8 | GPIO_PIN_9;
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLUP;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    g.Alternate = GPIO_AF7_USART3;
    HAL_GPIO_Init(GPIOD, &g);
    huart3.Instance = USART3;
    huart3.Init.BaudRate = 921600;
    huart3.Init.WordLength = UART_WORDLENGTH_8B;
    huart3.Init.StopBits = UART_STOPBITS_1;
    huart3.Init.Parity = UART_PARITY_NONE;
    huart3.Init.Mode = UART_MODE_TX_RX;
    huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart3.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&huart3) != HAL_OK) for (;;) {}
}

int main(void) {
    HAL_Init();
    clock_init();
    uart_init();
    uint8_t out[HIL_FRAME_MAX(sizeof(hil_build_info_t))];
    for (;;) {
        if (USART3->ISR & USART_ISR_ORE) USART3->ICR = USART_ICR_ORECF;
        if (USART3->ISR & USART_ISR_RXNE_RXFNE) {
            size_t n = hil_hello_feed(&link_state, 2, (uint8_t)USART3->RDR, out);
            if (n) HAL_UART_Transmit(&huart3, out, (uint16_t)n, 100);
        }
    }
}
