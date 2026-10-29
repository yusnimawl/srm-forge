/* Exports of the Nucleo's AHB compare rule and the SIL converter's carrier rule for the host test. */
#include <math.h>
#include <string.h>

#include "pwm_compare.h"
#include "srm_sim.h"

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT void shim_ahb_compare(float duty, int chop_soft, uint16_t arr, uint16_t *ccr_upper, uint16_t *ccr_lower)
{
    ahb_compare(duty, chop_soft, arr, ccr_upper, ccr_lower);
}

/* The SIL's switch states (no delays) at carrier = j / arr, j = 0..arr, the arr + 1 points of half a carrier period:
 * up[j], lo[j]. */
EXPORT void shim_sil_states(double duty, int chop_soft, int arr, uint8_t *up, uint8_t *lo)
{
    srm_sim_config_t cfg;
    srm_conv_t conv;
    memset(&cfg, 0, sizeof cfg);
    cfg.n_phases = 1;
    cfg.pwm_hz = 1.0;
    cfg.controller_clock = 1.0;
    cfg.dt = 1.0;
    srm_conv_init(&conv, &cfg);
    srm_conv_set_pwm(&conv, 0, duty, chop_soft);
    for (int j = 0; j <= arr; j++) {
        srm_conv_step(&conv, 0.5 * (double)j / (double)arr);
        up[j] = (uint8_t)conv.ph[0].u_eff;
        lo[j] = (uint8_t)conv.ph[0].l_eff;
    }
}
