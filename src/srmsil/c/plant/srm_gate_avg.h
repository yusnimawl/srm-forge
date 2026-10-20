#ifndef SRM_GATE_AVG_H
#define SRM_GATE_AVG_H

#include <stdint.h>

#include "srm_plant.h"

/* A commanded gate word valid from tick t. Bit k is the upper switch of phase k, bit 8 + k its lower switch. */
typedef struct {
    uint64_t t;
    uint16_t gates;
} srm_edge_t;

/* Commanded and effective gate words and, per switch, the tick at which a pending command reaches the switch. A
   command reaches the switch rise_ticks (on) or fall_ticks (off) after it was issued, provided no later command
   arrives by then. */
typedef struct {
    uint16_t cmd, eff;
    uint64_t pending_t[16];
    uint16_t pending_valid;
    int64_t rise_ticks, fall_ticks;
} srm_gate_avg_t;

void srm_gate_avg_init(srm_gate_avg_t *g, int64_t rise_ticks, int64_t fall_ticks, uint16_t initial);

/* Consumes the sorted edges with t in [t0, t0 + dt) (dt ticks of c->dt / dt seconds) and writes, for each phase, the
   winding voltage averaged over the window and the fractions of the window each switch is on. The flux starts at
   psi0 and follows the asymmetric half-bridge voltage segment by segment (resistive drop neglected); freewheeling
   and demagnetising conduct only while the running flux is positive, and the flux stops at zero. The voltage is
   (end flux - psi0) / c->dt. Pending commands that mature after the window stay pending. */
void srm_gate_avg_window(srm_gate_avg_t *g, const srm_sim_config_t *c, const srm_edge_t *edges, int n, uint64_t t0,
                         uint64_t dt, const double *psi0, double *v_out, float *on_upper, float *on_lower);

#endif
