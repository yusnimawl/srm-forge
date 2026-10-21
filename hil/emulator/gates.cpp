// Gate inputs: Teensy pins 14..21 are fast GPIO6 bits 16..19, 22, 23, 26, 27 and share the combined GPIO6-9
// interrupt, which this file owns (attachInterrupt() would replace the handler).
#include <Arduino.h>

#include "emu.h"

static const uint32_t GATE_BITS = (1u << 16) | (1u << 17) | (1u << 18) | (1u << 19) | (1u << 22) | (1u << 23) |
                                  (1u << 26) | (1u << 27);

static void gate_isr()
{
    const uint32_t t = ARM_DWT_CYCCNT;
    GPIO6_ISR = GPIO6_ISR & GATE_BITS;      // clear first, so a change while reading raises the interrupt again
    const uint32_t psr = GPIO6_PSR;
    if (!g_selftest) emu_edge_push(&g_edges, t, emu_gate_word(psr));
    asm volatile("dsb");
}

void gates_begin(void)
{
    for (int p = 14; p <= 21; p++) pinMode(p, INPUT_PULLDOWN);
    GPIO6_IMR &= ~GATE_BITS;
    GPIO6_EDGE_SEL |= GATE_BITS;
    GPIO6_ISR = GATE_BITS;
    attachInterruptVector(IRQ_GPIO6789, gate_isr);
    NVIC_SET_PRIORITY(IRQ_GPIO6789, EMU_PRIO_GATES);
    NVIC_ENABLE_IRQ(IRQ_GPIO6789);
    GPIO6_IMR |= GATE_BITS;
}
