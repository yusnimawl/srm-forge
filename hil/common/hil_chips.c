#include "hil_chips.h"

#include <math.h>

#define TWO_PI 6.283185307179586476925286766559

static double round_away(double x) { return x < 0.0 ? -floor(-x + 0.5) : floor(x + 0.5); }

/* NaN clips to 0, which lies inside every code range used here: converting NaN to an integer is undefined in C. */
static double clip(double x, double lo, double hi) { return x != x ? 0.0 : (x < lo ? lo : (x > hi ? hi : x)); }

static int clamp_bits(int bits) { return bits < 10 ? 10 : (bits > 16 ? 16 : bits); }

int16_t ad7606_code(double volts, double range_v)
{
    return (int16_t)clip(round_away(volts / range_v * 32768.0), -32768.0, 32767.0);
}

uint16_t ad7606_to_unsigned(int16_t code) { return (uint16_t)((int32_t)code + 32768); }

uint16_t ad2s1210_position(double elec_angle, int bits) { return ad2s1210_position_turns(elec_angle / TWO_PI, bits); }

uint16_t ad2s1210_position_turns(double turns, int bits)
{
    bits = clamp_bits(bits);
    double n = (double)(1u << bits);
    turns -= floor(turns);
    double code = round_away(turns * n);
    if (!(code < n))      /* a full turn, or NaN */
        code = 0.0;
    return (uint16_t)((uint32_t)code << (16 - bits));
}

double ad2s1210_angle(uint16_t word, int bits)
{
    bits = clamp_bits(bits);
    return (double)(word >> (16 - bits)) * TWO_PI / (double)(1u << bits);
}

int16_t ad2s1210_velocity(double elec_rad_s, int bits, double max_rps)
{
    bits = clamp_bits(bits);
    double half = (double)(1u << (bits - 1));
    double code = clip(round_away(elec_rad_s / TWO_PI / max_rps * half), -half, half - 1.0);
    return (int16_t)((int32_t)code * (1 << (16 - bits)));
}

uint16_t mcp492x_word(int channel, uint16_t code12)
{
    return (uint16_t)(((channel ? 1u : 0u) << 15) | (1u << 13) | (1u << 12) | (code12 & 0x0FFFu));
}

uint16_t dac_code(double amps, double v_mid, double v_per_a, double vref)
{
    return (uint16_t)clip(round_away((v_mid + v_per_a * amps) / vref * 4096.0), 0.0, 4095.0);
}
