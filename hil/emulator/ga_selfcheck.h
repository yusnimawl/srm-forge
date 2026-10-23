/* Self-check of the gate averager as compiled into the firmware (portable C99, tested on the host).
 *
 * emu_ga_selfcheck runs the float averager (srm_gate_avg.c with SRM_TABLE_FLOAT) over a fixed set of windows and
 * returns an FNV-1a hash of every winding voltage and of the effective and pending switch words after each window.
 * EMU_GA_SELFCHECK_HASH is that hash from the host build (tests/hil/test_hil_ga_selfcheck.py checks it); the Teensy
 * build gives the same value at 912 MHz with arm-none-eabi-gcc 15.2.1 (Arm GNU Toolchain 15.2.Rel1) at -O3, also
 * with advance_all in srm_gate_avg.c kept out of line. emu_start runs it at every START and refuses with HIL_ERROR
 * on a different value: the averager was compiled wrongly, or the processor computed wrongly. At 1008 MHz the
 * iMXRT1062 fails timing in the first windows of a check that starts after light load, and the check refused such
 * STARTs (docs/r8b-hil-results.md, Step 1d); a passing check does not prove timing margin.
 *
 * The reference relies on FMA contraction in both builds: the host's zig cc (clang, native target) and the Teensy's
 * GCC (fpv5) both fuse p += v * tau into one fused multiply-add. A host without FMA, or a change of the contraction
 * settings on either side, gives another hash: the host test fails or the emulator refuses START, both on the safe
 * side. */
#ifndef GA_SELFCHECK_H
#define GA_SELFCHECK_H

#include <stdint.h>

#define EMU_GA_SELFCHECK_HASH 0x3e067992u

#ifdef __cplusplus
extern "C" {
#endif

uint32_t emu_ga_selfcheck(void);

#ifdef __cplusplus
}
#endif

#endif
