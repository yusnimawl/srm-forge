/* Exports of the protocol sizes for the host test (the protocol functions export themselves through this unit). */
#include "hil_proto.h"

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT size_t shim_frame(uint8_t type, uint16_t seq, const void *p, size_t n, uint8_t *out)
{
    return hil_frame(type, seq, p, n, out);
}

EXPORT long shim_unframe(const uint8_t *f, size_t n, uint8_t *type, uint16_t *seq, uint8_t *payload, size_t cap)
{
    return hil_unframe(f, n, type, seq, payload, cap);
}

EXPORT size_t shim_payload_size(uint8_t type) { return hil_payload_size(type); }
EXPORT uint16_t shim_crc16(const uint8_t *p, size_t n) { return hil_crc16(p, n); }
EXPORT size_t shim_cobs_encode(const uint8_t *in, size_t n, uint8_t *out) { return hil_cobs_encode(in, n, out); }
EXPORT long shim_cobs_decode(const uint8_t *in, size_t n, uint8_t *out) { return hil_cobs_decode(in, n, out); }
EXPORT size_t shim_sample_size(void) { return sizeof(hil_sample_t); }
