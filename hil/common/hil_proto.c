#include "hil_proto.h"

size_t hil_cobs_encode(const uint8_t *in, size_t n, uint8_t *out)
{
    size_t code_at = 0, w = 1;
    uint8_t code = 1;
    for (size_t r = 0; r < n; r++) {
        if (in[r] == 0) {
            out[code_at] = code;
            code_at = w++;
            code = 1;
        } else {
            out[w++] = in[r];
            if (++code == 0xFF) {
                out[code_at] = code;
                code_at = w++;
                code = 1;
            }
        }
    }
    out[code_at] = code;
    return w;
}

long hil_cobs_decode(const uint8_t *in, size_t n, uint8_t *out)
{
    size_t r = 0, w = 0;
    while (r < n) {
        uint8_t code = in[r++];
        if (code == 0 || r + (size_t)(code - 1) > n)
            return -1;
        for (uint8_t i = 1; i < code; i++) {
            if (in[r] == 0)
                return -1;
            out[w++] = in[r++];
        }
        if (code != 0xFF && r < n)
            out[w++] = 0;
    }
    return (long)w;
}

uint16_t hil_crc16(const uint8_t *p, size_t n)
{
    uint16_t crc = 0xFFFF;
    while (n--) {
        crc ^= (uint16_t)(*p++ << 8);
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

size_t hil_frame(uint8_t type, uint16_t seq, const void *payload, size_t n, uint8_t *out)
{
    uint8_t raw[HIL_PAYLOAD_MAX + 5];
    const uint8_t *p = (const uint8_t *)payload;
    raw[0] = type;
    raw[1] = (uint8_t)seq;
    raw[2] = (uint8_t)(seq >> 8);
    for (size_t i = 0; i < n; i++)
        raw[3 + i] = p[i];
    uint16_t crc = hil_crc16(raw, n + 3);
    raw[3 + n] = (uint8_t)crc;
    raw[4 + n] = (uint8_t)(crc >> 8);
    size_t m = hil_cobs_encode(raw, n + 5, out);
    out[m] = 0;
    return m + 1;
}

long hil_unframe(const uint8_t *frame, size_t n, uint8_t *type, uint16_t *seq, uint8_t *payload, size_t cap)
{
    uint8_t raw[HIL_PAYLOAD_MAX + 5];
    if (n > 0 && frame[n - 1] == 0)
        n--;
    if (n > HIL_FRAME_MAX(HIL_PAYLOAD_MAX))
        return -3;
    long m = hil_cobs_decode(frame, n, raw);
    if (m < 5)
        return -1;
    size_t len = (size_t)m - 5;
    if (hil_crc16(raw, (size_t)m - 2) != (uint16_t)(raw[m - 2] | (raw[m - 1] << 8)))
        return -2;
    if (len > cap || len > HIL_PAYLOAD_MAX)
        return -3;
    *type = raw[0];
    *seq = (uint16_t)(raw[1] | (raw[2] << 8));
    for (size_t i = 0; i < len; i++)
        payload[i] = raw[3 + i];
    return (long)len;
}

size_t hil_payload_size(uint8_t type)
{
    switch (type) {
    case HIL_BUILD_INFO: return sizeof(hil_build_info_t);
    case HIL_EMU_CONFIG: return sizeof(hil_emu_config_t);
    case HIL_TABLE_CHUNK: return sizeof(hil_table_chunk_t);
    case HIL_PARAM_SET: return sizeof(hil_param_set_t);
    case HIL_PARAM_REPLY: return sizeof(hil_param_reply_t);
    case HIL_COMMAND: return sizeof(hil_command_t);
    case HIL_LIVE_EMU: return sizeof(hil_live_emu_t);
    case HIL_LIVE_CTRL: return sizeof(hil_live_ctrl_t);
    case HIL_CAPTURE_HDR: return sizeof(hil_capture_hdr_t);
    default: return 0;
    }
}
