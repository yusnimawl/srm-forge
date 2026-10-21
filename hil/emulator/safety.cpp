// RUN (pin 7, from the controller) and READY (pin 8, to the controller). RUN low holds the plant and presents the
// zero-current outputs; READY is high only while running without a fault.
#include <Arduino.h>

#include "emu.h"

#define PIN_RUN 7
#define PIN_READY 8

void safety_begin(void)
{
    pinMode(PIN_RUN, INPUT_PULLDOWN);
    pinMode(PIN_READY, OUTPUT);
    digitalWriteFast(PIN_READY, LOW);
}

bool safety_run(void) { return g_selftest || digitalReadFast(PIN_RUN); }

void safety_ready(bool on) { digitalWriteFast(PIN_READY, on ? HIGH : LOW); }
