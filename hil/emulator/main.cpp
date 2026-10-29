// Teensy 4.1 motor emulator (see emu.h).
#include <Arduino.h>

#include "emu.h"

void setup()
{
    safety_begin();
    link_begin();
    outputs_begin();
    gates_begin();
}

void loop() { link_poll(); }
