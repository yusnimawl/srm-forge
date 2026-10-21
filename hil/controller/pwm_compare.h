/* Compare values of the asymmetric half-bridge PWM (portable C99, tested on the host).
 *
 * TIM1 (upper switches) and TIM8 (lower switches) count 0..arr..0 (centre-aligned), output active while CNT < CCR
 * (PWM mode 1), with the update event at the underflow. The SIL's carrier is then 1 - CNT / arr: its rule "upper on
 * while carrier > 1 - duty" is "on while CNT < arr * duty", so the on-pulse is centred on the underflow, where the
 * driver samples. CCR = 0 is always off, CCR = arr + 1 always on. */
#ifndef PWM_COMPARE_H
#define PWM_COMPARE_H

#include <stdint.h>

/* Duty is clipped to [0, 1] (NaN is 0). Soft chopping keeps the lower switch on (ccr_lower = arr + 1); hard chopping
 * switches it with the upper one (ccr_lower = ccr_upper). arr must be at most 65534. */
void ahb_compare(float duty, int chop_soft, uint16_t arr, uint16_t *ccr_upper, uint16_t *ccr_lower);

#endif
