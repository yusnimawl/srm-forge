/* Self-check of the gate averager as compiled into the firmware (portable C99, tested on the host).
 *
 * emu_ga_selfcheck runs the float averager (srm_gate_avg.c with SRM_TABLE_FLOAT) over a fixed set of windows and
 * returns an FNV-1a hash of every winding voltage and of the effective and pending switch words after each window.
 * EMU_GA_SELFCHECK_HASH is that hash from the host build (tests/hil/test_hil_ga_selfcheck.py checks it); the Teensy
 * build was checked to give the same value with arm-none-eabi-gcc 15.2.1 (Arm GNU Toolchain 15.2.Rel1) at -O3, and a
 * different one when advance_all in srm_gate_avg.c is inlined. emu_start runs it at every START and refuses with
 * HIL_ERROR on a different value: the averager was compiled wrongly.
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
