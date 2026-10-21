#include "pwm_compare.h"

void ahb_compare(float duty, int chop_soft, uint16_t arr, uint16_t *ccr_upper, uint16_t *ccr_lower)
{
    uint16_t u;
    if (!(duty > 0.0f)) {                /* also NaN */
        u = 0;
    } else if (duty >= 1.0f) {
        u = (uint16_t)(arr + 1u);
    } else {
        /* on while CNT < arr * duty: the smallest integer not below arr * duty */
        const float x = (float)arr * duty;
        uint32_t c = (uint32_t)x;
        if ((float)c < x) c++;
        u = (uint16_t)(c > arr ? arr : c);
    }
    *ccr_upper = u;
    *ccr_lower = chop_soft ? (uint16_t)(arr + 1u) : u;
}
