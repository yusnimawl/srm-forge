/* Quadrature encoder edge schedule of one emulator step (portable C99, tested on the host).
 *
 * The count position is c(theta) = (theta + offset + ecc_amp * sin(ecc_harm * theta)) * cpr / (2 pi), the measured
 * angle of the SIL encoder model (srm_sensors.c); the count is floor(c), one quadrature edge per count, so a timer in
 * x4 encoder mode with ARR = cpr - 1 reads the SIL's srm_encoder_count. */
#ifndef ENC_SCHED_H
#define ENC_SCHED_H

#include <stdint.h>

#define ENC_A 1u
#define ENC_B 2u
#define ENC_Z 4u

#ifdef __cplusplus
extern "C" {
#endif

/* Count position c(theta) (fractional counts, unwrapped). */
double enc_position(double theta, uint32_t cpr, double offset, double ecc_amp, int ecc_harm);
/* Output state of a count: A and B in Gray order (A leads while the count rises), Z while count mod cpr is 0. */
uint8_t enc_state(int64_t count, uint32_t cpr);
/* Every count boundary crossed from theta0 to theta1 (either direction), at times interpolated linearly in count
 * position over [t0, t0 + dt], with the state after each edge. Returns the number of edges, -1 if more than cap
 * (nothing written past cap), 0 when cpr is 0. */
int enc_edges(double theta0, double theta1, uint32_t cpr, double offset, double ecc_amp, int ecc_harm, double t0,
              double dt, double *times, uint8_t *states, int cap);
/* The same from the count positions c0 = c(theta0) and c1 = c(theta1). */
int enc_edges_c(double c0, double c1, uint32_t cpr, double t0, double dt, double *times, uint8_t *states, int cap);

/* Output-compare decisions on a free-running 32-bit tick counter (wrap-safe). enc_edge_due: an edge at `tick` is due
 * or past at counter `now`, so it is put out at once rather than programmed (a compare set in the past would match
 * only a counter wrap later). enc_compare_missed: the compare programmed for `due` should have matched more than
 * `slack` ticks before `now`. */
int enc_edge_due(uint32_t tick, uint32_t now);
int enc_compare_missed(uint32_t due, uint32_t now, uint32_t slack);
/* Next queued edge at `tick`, with `last` a tick the counter has reached (the compare that fired): ENC_PUT it now
 * (due), ENC_PROGRAM the compare (more than `near` ticks ahead), or ENC_CHECK the counter first (enc_edge_due). */
#define ENC_PUT 0
#define ENC_PROGRAM 1
#define ENC_CHECK 2
int enc_next_action(uint32_t tick, uint32_t last, uint32_t near);

#ifdef __cplusplus
}
#endif

#endif
