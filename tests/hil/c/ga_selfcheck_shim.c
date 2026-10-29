/* Export of the emulator's gate-averager self-check for the host test. */
#include "ga_selfcheck.h"

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT uint32_t shim_ga_selfcheck(void) { return emu_ga_selfcheck(); }
