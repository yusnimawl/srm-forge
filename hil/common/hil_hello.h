/* Byte-stream front end shared by both boards: collects one frame at a time and answers HIL_HELLO with HIL_BUILD_INFO. */
#ifndef HIL_HELLO_H
#define HIL_HELLO_H

#include <stdint.h>
#include "hil_proto.h"

#ifdef HIL_CURRENT_SENSE_INTERNAL
#define HIL_CS_CODE 1
#else
#define HIL_CS_CODE 0
#endif

#if defined(HIL_POSITION_ENCODER) && defined(HIL_POSITION_AD2S1210)
#define HIL_POS_CODE 2
#elif defined(HIL_POSITION_AD2S1210)
#define HIL_POS_CODE 1
#else
#define HIL_POS_CODE 0
#endif

#if defined(HIL_CURRENT_SENSE_INTERNAL) && defined(HIL_DAC_MCP4921X4)
#define HIL_DAC_CODE 2
#elif defined(HIL_CURRENT_SENSE_INTERNAL)
#define HIL_DAC_CODE 1
#else
#define HIL_DAC_CODE 0
#endif

#ifndef HIL_FIRMWARE_HASH
#define HIL_FIRMWARE_HASH 0
#endif

typedef struct {
    uint8_t buf[HIL_FRAME_MAX(HIL_PAYLOAD_MAX)];
    uint16_t n;
    uint16_t seq_out;
} hil_hello_t;

/* Feed one received byte. When it completes a HELLO frame, writes the BUILD_INFO frame to `out` (HIL_FRAME_MAX(16)
 * bytes) and returns its length; returns 0 otherwise. */
static inline size_t hil_hello_feed(hil_hello_t *h, uint8_t board, uint8_t byte, uint8_t *out) {
    if (byte != 0) {
        if (h->n < sizeof h->buf) h->buf[h->n++] = byte;
        else h->n = 0;
        return 0;
    }
    uint8_t type = 0, payload[HIL_PAYLOAD_MAX];
    uint16_t seq = 0;
    long len = h->n ? hil_unframe(h->buf, h->n, &type, &seq, payload, sizeof payload) : -1;
    h->n = 0;
    if (len < 0 || type != HIL_HELLO) return 0;
    hil_build_info_t info = {HIL_PROTOCOL_VERSION, board, HIL_CS_CODE, HIL_POS_CODE, HIL_DAC_CODE, HIL_FIRMWARE_HASH};
    return hil_frame(HIL_BUILD_INFO, seq, &info, sizeof info, out);
}

#endif
