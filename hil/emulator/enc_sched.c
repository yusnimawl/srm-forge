#include "enc_sched.h"

#include <math.h>

#define TWO_PI 6.283185307179586476925286766559

static const uint8_t GRAY[4] = {0u, 1u, 3u, 2u};    /* (A | B << 1) of count n mod 4: A leads while the count rises */

double enc_position(double theta, uint32_t cpr, double offset, double ecc_amp, int ecc_harm)
{
    double m = theta + offset;
    if (ecc_amp != 0.0) m += ecc_amp * sin((double)ecc_harm * theta);
    return m * (double)cpr * (1.0 / TWO_PI);
}

/* State of an integer-valued count held in a double: no 64-bit integer arithmetic (library calls on the Cortex-M7).
   Exact while |count| < 2^52. */
static uint8_t state_d(double count, double cpr, double inv_cpr)
{
    const int g = (int)(count - 4.0 * floor(count * 0.25));
    const double k = floor(count * inv_cpr + 0.5);       /* nearest whole turn; Z when it is the count exactly */
    return (uint8_t)(GRAY[g & 3] | (k * cpr == count ? ENC_Z : 0u));
}

uint8_t enc_state(int64_t count, uint32_t cpr)
{
    return cpr ? state_d((double)count, (double)cpr, 1.0 / (double)cpr) : GRAY[count & 3];
}

int enc_edges(double theta0, double theta1, uint32_t cpr, double offset, double ecc_amp, int ecc_harm, double t0,
              double dt, double *times, uint8_t *states, int cap)
{
    if (cpr == 0) return 0;
    return enc_edges_c(enc_position(theta0, cpr, offset, ecc_amp, ecc_harm),
                       enc_position(theta1, cpr, offset, ecc_amp, ecc_harm), cpr, t0, dt, times, states, cap);
}

int enc_edges_c(double c0, double c1, uint32_t cpr, double t0, double dt, double *times, uint8_t *states, int cap)
{
    if (cpr == 0) return 0;
    /* Most steps cross no boundary: decide that in double, before any 64-bit conversion or division (slow on the
       Cortex-M7). */
    const double f0 = floor(c0), f1 = floor(c1);
    if (f0 == f1) return 0;
    const int up = f1 > f0;
    const double dn = up ? f1 - f0 : f0 - f1;
    if (dn > (double)cap) return -1;
    const int n = (int)dn;
    const double k_t = dt / (c1 - c0), dcpr = (double)cpr, inv_cpr = 1.0 / dcpr;
    for (int j = 0; j < n; j++) {
        /* rising: boundary f0 + 1 + j enters that count; falling: boundary f0 - j leaves it for the one below */
        const double b = up ? f0 + 1.0 + (double)j : f0 - (double)j;
        times[j] = t0 + (b - c0) * k_t;
        states[j] = state_d(up ? b : b - 1.0, dcpr, inv_cpr);
    }
    return n;
}
