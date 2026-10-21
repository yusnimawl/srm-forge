// USB link: framed requests, live statistics at 20 Hz and captures.
//
// EMU_CONFIG, START, STOP and COMMAND are acknowledged with an empty frame of the same type and sequence number; a
// refused request (and a refused TABLE_CHUNK) gets HIL_ERROR with a text and the request's sequence number.
// CAPTURE_REQ (hil_capture_req_t) starts a capture at the next step while running: CAPTURE_HDR, CAPTURE_DATA packets
// with sequence numbers 0, 1, 2, ... and CAPTURE_END (hil_capture_end_t). A capture that fits the ring is sent after
// it is recorded; a longer one is sent while it records, and a full ring ends it as invalid.
#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "emu.h"
extern "C" {
#include "hil_hello.h"
}

#define RING_MASK (EMU_CAPTURE_RING - 1u)

DMAMEM static hil_sample_t ring[EMU_CAPTURE_RING];
static volatile uint32_t head, tail, remaining, recorded, dropped;
static volatile bool cap_on, cap_bad;
static bool sending, buffered;
static uint32_t cap_n, overruns_at_start;
static uint16_t data_seq, seq_out;

static uint8_t rx[HIL_FRAME_MAX(HIL_PAYLOAD_MAX)];
static size_t rx_n;
static bool rx_overflow;
static uint8_t tx[HIL_FRAME_MAX(HIL_PAYLOAD_MAX)];
static uint8_t pkt[HIL_PAYLOAD_MAX];

static void send(uint8_t type, uint16_t seq, const void *p, size_t n)
{
    size_t m = hil_frame(type, seq, p, n, tx);
    Serial.write(tx, m);
}

static void reply(uint8_t type, uint16_t seq, const char *err)
{
    if (err) send(HIL_ERROR, seq, err, strlen(err));
    else send(type, seq, NULL, 0);
}

bool cap_wants_sample(void) { return cap_on; }

void cap_push(const hil_sample_t *s)
{
    const uint32_t h = head;
    if (h - tail >= EMU_CAPTURE_RING) {
        dropped++;
        cap_bad = true;
        cap_on = false;
        return;
    }
    ring[h & RING_MASK] = *s;
    head = h + 1;
    recorded++;
    if (--remaining == 0) cap_on = false;
}

uint32_t cap_dropped(void) { return dropped; }

void cap_abort(void)
{
    if (cap_on) {
        cap_on = false;
        cap_bad = true;
    }
}

static const char *capture_start(const uint8_t *p, long len)
{
    if (!emu_running()) return "capture refused: not running";
    if (sending) return "capture refused: a capture is in progress";
    hil_capture_req_t r = {0};
    if (len == (long)sizeof r) memcpy(&r, p, sizeof r);
    else if (len != 0) return "capture refused: bad request";
    uint32_t n = r.n_steps ? r.n_steps : emu_capture_default_steps();
    if (n == 0) return "capture refused: zero steps";
    hil_capture_hdr_t hdr = emu_capture_header(n);
    send(HIL_CAPTURE_HDR, 0, &hdr, sizeof hdr);
    cap_n = n;
    buffered = n <= EMU_CAPTURE_RING;
    head = tail = recorded = 0;
    remaining = n;
    cap_bad = false;
    overruns_at_start = emu_overruns();
    data_seq = 0;
    sending = true;
    asm volatile("dmb" ::: "memory");
    cap_on = true;
    return NULL;
}

static void capture_pump(void)
{
    if (!sending) return;
    const bool done = !cap_on;
    if (buffered && !done) return;
    for (;;) {
        uint32_t avail = head - tail;
        if (avail == 0 || (avail < HIL_CAPTURE_SAMPLES_PER_PACKET && !done)) break;
        uint32_t k = avail < HIL_CAPTURE_SAMPLES_PER_PACKET ? avail : HIL_CAPTURE_SAMPLES_PER_PACKET;
        uint32_t t = tail;
        memcpy(pkt, &ring[t & RING_MASK].step, 4);
        for (uint32_t j = 0; j < k; j++) memcpy(pkt + 4 + j * sizeof(hil_sample_t), &ring[(t + j) & RING_MASK], sizeof(hil_sample_t));
        send(HIL_CAPTURE_DATA, data_seq++, pkt, 4 + k * sizeof(hil_sample_t));
        tail = t + k;
        if (!done && head - tail < HIL_CAPTURE_SAMPLES_PER_PACKET) break;
    }
    if (done && head == tail) {
        hil_capture_end_t e;
        e.n_steps = recorded;
        e.valid = !cap_bad && recorded == cap_n && emu_overruns() == overruns_at_start;
        send(HIL_CAPTURE_END, data_seq, &e, sizeof e);
        sending = false;
    }
}

static void dispatch(uint8_t type, uint16_t seq, const uint8_t *p, long len)
{
    const size_t want = hil_payload_size(type);
    if (want && (size_t)len != want) {
        reply(type, seq, "bad payload size");
        return;
    }
    switch (type) {
    case HIL_HELLO: {
        hil_build_info_t info = {HIL_PROTOCOL_VERSION, 1, HIL_CS_CODE, HIL_POS_CODE, HIL_DAC_CODE, HIL_FIRMWARE_HASH};
        send(HIL_BUILD_INFO, seq, &info, sizeof info);
        break;
    }
    case HIL_EMU_CONFIG: {
        hil_emu_config_t c;
        memcpy(&c, p, sizeof c);
        reply(type, seq, emu_configure(&c));
        break;
    }
    case HIL_TABLE_CHUNK: {
        static hil_table_chunk_t c;
        memcpy(&c, p, sizeof c);
        const char *err = emu_table_chunk(&c);
        if (err) reply(type, seq, err);
        break;
    }
    case HIL_START: reply(type, seq, emu_start()); break;
    case HIL_STOP:
        emu_stop();
        reply(type, seq, NULL);
        break;
    case HIL_COMMAND: {
        hil_command_t c;
        memcpy(&c, p, sizeof c);
        if (c.mode == HIL_CMD_EMU_SELFTEST_PHASES && c.value >= 1.0f && c.value <= 15.0f) {
            emu_set_selftest_phases((unsigned)c.value);
            reply(type, seq, NULL);
            break;
        }
        if (c.mode != HIL_CMD_EMU_SELFTEST || !(c.value == c.value)) {
            reply(type, seq, "command refused: unknown mode");
            break;
        }
        emu_set_selftest(c.value);
        reply(type, seq, NULL);
        break;
    }
    case HIL_CAPTURE_REQ: {
        const char *err = capture_start(p, len);
        if (err) reply(type, seq, err);
        break;
    }
    default: reply(type, seq, "unknown request");
    }
}

void link_begin(void) { Serial.begin(115200); }

void link_poll(void)
{
    static uint8_t payload[HIL_PAYLOAD_MAX];
    while (Serial.available()) {
        const uint8_t b = (uint8_t)Serial.read();
        if (b != 0) {
            if (rx_n < sizeof rx) rx[rx_n++] = b;
            else rx_overflow = true;
            continue;
        }
        uint8_t type = 0;
        uint16_t seq = 0;
        long len = (rx_n && !rx_overflow) ? hil_unframe(rx, rx_n, &type, &seq, payload, sizeof payload) : -1;
        rx_n = 0;
        rx_overflow = false;
        if (len >= 0) dispatch(type, seq, payload, len);
    }
    if (emu_take_overload()) {
        char msg[160];
        uint32_t ga[3], pl[3];
        emu_profile(ga, pl);
        int n = snprintf(msg, sizeof msg, "stopped: the step loop fell behind (step max %.2f us; cycles max/mean: "
                         "gate averaging %lu/%lu, plant %lu/%lu, step mean %lu)", (double)emu_step_max_us(),
                         (unsigned long)ga[0], (unsigned long)ga[1], (unsigned long)pl[0], (unsigned long)pl[1],
                         (unsigned long)ga[2]);
        send(HIL_ERROR, seq_out++, msg, (size_t)n);
    }
    hil_live_emu_t live;
    if (emu_running() && emu_live_take(&live)) send(HIL_LIVE_EMU, seq_out++, &live, sizeof live);
    capture_pump();
}
