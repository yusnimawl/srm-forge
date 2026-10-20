/* Coding of the converter chips the emulator imitates: AD7606 (ADC), AD2S1210 (resolver-to-digital),
   MCP4921/4922 (DAC). Plain C99, no allocation, no platform headers. Codes round half away from zero
   and clip at the code range. */
#ifndef HIL_CHIPS_H
#define HIL_CHIPS_H

#include <stdint.h>

/* Two's complement code of a voltage for a +-range_v input range; 1 LSB = range_v / 32768. */
int16_t ad7606_code(double volts, double range_v);
/* Offset-binary form (code + 32768) handed to the controller's ADC read. */
uint16_t ad7606_to_unsigned(int16_t code);

/* Electrical angle wrapped to [0, 2 pi), quantised to `bits` (10..16), MSB-aligned in 16 bits. */
uint16_t ad2s1210_position(double elec_angle, int bits);
/* Angle in [0, 2 pi) of a position word at `bits` resolution. */
double ad2s1210_angle(uint16_t word, int bits);
/* Two's complement velocity, full scale +-max_rps, quantised to `bits`, MSB-aligned in 16 bits. */
int16_t ad2s1210_velocity(double elec_rad_s, int bits, double max_rps);

/* MCP492x command word: channel bit 15 (0 = A, 1 = B), BUF = 0, GA = 1 (1x), SHDN = 1, 12-bit code. */
uint16_t mcp492x_word(int channel, uint16_t code12);
/* 12-bit DAC code for v_mid + v_per_a * amps volts with reference vref, clipped to [0, 4095]. */
uint16_t dac_code(double amps, double v_mid, double v_per_a, double vref);

#endif
