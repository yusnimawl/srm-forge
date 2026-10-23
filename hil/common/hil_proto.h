/* Framed PC protocol shared by the emulator and controller firmware and the Python host (srmsil.hil.proto).
 *
 * Frame on the wire: COBS(type, seq LE, payload, CRC-16 LE) followed by one 0x00. The CRC (CCITT-FALSE) covers
 * type, seq and payload and is computed before COBS. All payloads are little-endian and packed. */
#ifndef HIL_PROTO_H
#define HIL_PROTO_H

#include <stddef.h>
#include <stdint.h>

#define HIL_PROTOCOL_VERSION 1
#define HIL_PAYLOAD_MAX 1024
/* Output buffer size hil_frame needs for an n-byte payload (COBS overhead plus type, seq, CRC and the delimiter). */
#define HIL_FRAME_MAX(n) ((n) + 5 + ((n) + 5) / 254 + 2)
#define HIL_CAPTURE_SAMPLES_PER_PACKET 28
#define HIL_TABLE_CHUNK_FLOATS 200

enum hil_type {
    HIL_HELLO = 1,
    HIL_BUILD_INFO,
    HIL_EMU_CONFIG,
    HIL_TABLE_CHUNK,
    HIL_PARAM_SET,
    HIL_PARAM_REPLY,
    HIL_COMMAND,
    HIL_START,
    HIL_STOP,
    HIL_LIVE_EMU,
    HIL_LIVE_CTRL,
    HIL_CAPTURE_REQ,
    HIL_CAPTURE_HDR,
    HIL_CAPTURE_DATA,
    HIL_CAPTURE_END,
    HIL_ERROR
};

#pragma pack(push, 1)

typedef struct {
    uint16_t protocol;
    uint8_t board;           /* 1 emulator, 2 controller */
    uint8_t current_sense;   /* 0 ad7606, 1 internal */
    uint8_t position;        /* 0 encoder, 1 ad2s1210, 2 both */
    uint8_t dac;             /* 0 none, 1 mcp4922 x2, 2 mcp4921 x4 */
    uint32_t firmware_hash;
} hil_build_info_t;

typedef struct {
    char name[24];
    float value;
} hil_param_set_t;

typedef struct {
    char name[24];
    int8_t status;
} hil_param_reply_t;

/* Controller: mode 0 torque (N*m), 1 speed (rad/s). Emulator: the HIL_CMD_EMU_* modes. */
typedef struct {
    uint8_t mode;
    float value;
} hil_command_t;

/* Emulator command: a software gate pattern (both switches of the selected phases, 20 kHz, duty = value, 0 = off)
 * replaces the gate inputs and the RUN input. */
#define HIL_CMD_EMU_SELFTEST 2
/* Emulator command: the phases of that pattern (value = bit mask 1..15, default 1 = phase A), set before it starts. */
#define HIL_CMD_EMU_SELFTEST_PHASES 3
/* Controller command: stop and reset the board once the acknowledgement is sent, so the controller's parameters and
 * command are the build's defaults again (value ignored, finite). The board answers HELLO again after its boot. */
#define HIL_CMD_CTRL_RESET 4

typedef struct {
    uint32_t step;
    float mean_torque;       /* N*m */
    float ripple_pct;
    float i_rms[4];          /* A */
    float speed_rpm;
    float step_mean_us, step_max_us;
    uint32_t overruns, dropped;
    float edge_jitter_ns, latency_us;
    float temp_c;            /* die temperature */
    float trigger_hz;        /* controller sample triggers per s by the emulator clock; NaN below 2 */
} hil_live_emu_t;

/* Controller statistics over one 50 ms window (the maximum and the overruns since the start). */
typedef struct {
    float isr_mean_us, isr_max_us;   /* ctrl_isr execution time */
    uint32_t isr_overruns;
    float command;           /* the last ctrl_command value */
    float i_meas[4];         /* A rms of the sampled phase currents */
    float sample_us;         /* mean time from the trigger to the start of ctrl_isr */
    uint32_t tx_dropped;     /* frames the controller could not queue for sending, since boot */
    uint8_t state;           /* HIL_CTRL_* bits */
} hil_live_ctrl_t;

#define HIL_CTRL_RUNNING 1u        /* the controller runs (RUN is high) */
#define HIL_CTRL_READY 2u          /* the READY input is high */
#define HIL_CTRL_READY_STOP 4u     /* READY fell during the last run and stopped it */
#define HIL_CTRL_STALL_STOP 8u     /* the last run stopped because the sample chain stalled */
#define HIL_CTRL_INDEX 16u         /* an encoder index pulse was seen since the start */
#define HIL_CTRL_HANG_STOP 32u     /* the last run stopped because ctrl_isr did not return */

typedef struct {
    float dt;                /* s per step */
    float i_scale, psi_scale, v_scale, t_scale, omega_scale;   /* physical unit per count of the sample fields */
    uint32_t n_steps;
    uint8_t n_phases;
} hil_capture_hdr_t;

typedef struct {
    uint32_t n_steps;        /* 0 = the config's capture_steps */
} hil_capture_req_t;

typedef struct {
    uint8_t valid;           /* 0 after a dropped sample, an overrun or a stop during the capture */
    uint32_t n_steps;        /* samples recorded */
} hil_capture_end_t;

/* theta is the rotor angle in [0, 2 pi) as theta / (2 pi) * 65536; the other fields are counts of the header's scales.
 * The sample of step n holds the state at the start of the step and the winding voltage averaged over it. */
typedef struct {
    uint32_t step;
    int16_t i[4], psi[4], v[4], torque;
    uint16_t theta;
    int16_t omega;
    uint16_t gates;
} hil_sample_t;

typedef struct {
    uint8_t which;           /* 0 current, 1 torque */
    uint32_t offset;         /* index of data[0] in the flattened table; chunks of a table go in order from 0 */
    uint16_t n;              /* valid entries of data */
    float data[HIL_TABLE_CHUNK_FLOATS];
} hil_table_chunk_t;

/* The plant, converter and sensor settings of the emulator, and its table grid. */
typedef struct {
    float resistance;                /* ohm, per phase */
    float bus_voltage;               /* V */
    float speed;                     /* rad/s, fixed-speed mode */
    float theta0;                    /* rad, initial rotor angle */
    float inertia;                   /* kg*m^2 */
    float friction;                  /* N*m*s/rad */
    float load;                      /* N*m */
    float load_step;                 /* N*m added at load_step_time */
    float load_step_time;            /* s */
    float v_switch, v_diode;         /* V, switch and diode drops */
    float dead_time;                 /* s */
    float turn_on_delay, turn_off_delay;   /* s */
    float theta_step;                /* rad, table angle pitch */
    float psi_step;                  /* Wb, table flux pitch */
    float psi_max;                   /* Wb */
    float i_max;                     /* A */
    float adc_noise;                 /* A rms on the sensed currents */
    float adc_offset_error;          /* A */
    float adc_gain_error;            /* relative */
    float sensor_delay;              /* s */
    float encoder_offset;            /* rad */
    float encoder_ecc_amp;           /* rad */
    float resolver_gain_mismatch;    /* relative */
    float resolver_phase_error;      /* rad */
    float ad7606_range_v;            /* V, full-scale of the AD7606 input range */
    float ad7606_t_conv_us;          /* us, conversion time */
    float sense_v_per_a;             /* V per A of the current sensor */
    float volt_divider;              /* sensed volts per bus volt */
    float volt_rc_tau;               /* s, filter on the sensed voltages */
    float dac_v_mid;                 /* V at DAC mid-scale */
    float dac_v_per_a;               /* V per A at the DAC output */
    float omega_max;                 /* rad/s the run may reach (0 = none); the capture's omega range is the largest
                                        of this, 2 |speed| and 100 rad/s */
    uint32_t n_theta, n_psi;         /* table grid */
    uint32_t encoder_cpr;            /* counts per revolution */
    uint32_t capture_steps;          /* steps recorded by a capture */
    uint32_t seed;
    uint8_t n_phases;
    uint8_t n_rotor_poles;
    uint8_t mode;                    /* 0 fixed speed, 1 dynamic */
    uint8_t rdc_bits;                /* resolver-to-digital resolution */
    uint8_t resolver_pole_pairs;
    uint8_t encoder_ecc_harmonic;
    uint8_t resolver;                /* 1 when the resolver channel is used */
} hil_emu_config_t;

#pragma pack(pop)

/* COBS encode n bytes; out needs n + n/254 + 1 bytes. Returns the encoded length (no delimiter). */
size_t hil_cobs_encode(const uint8_t *in, size_t n, uint8_t *out);
/* Decode; out needs n bytes. Returns the decoded length, -1 on a malformed frame. */
long hil_cobs_decode(const uint8_t *in, size_t n, uint8_t *out);
uint16_t hil_crc16(const uint8_t *p, size_t n);
/* Build a frame including the trailing 0x00; out needs HIL_FRAME_MAX(n) bytes. Returns its length, 0 when n > HIL_PAYLOAD_MAX. */
size_t hil_frame(uint8_t type, uint16_t seq, const void *payload, size_t n, uint8_t *out);
/* Parse a frame (the trailing 0x00 is optional). Returns the payload length, -1 COBS error, -2 CRC error,
 * -3 payload longer than cap or HIL_PAYLOAD_MAX. */
long hil_unframe(const uint8_t *frame, size_t n, uint8_t *type, uint16_t *seq, uint8_t *payload, size_t cap);
/* Payload size of a fixed-size type; 0 for variable-length and empty types. */
size_t hil_payload_size(uint8_t type);

#endif
