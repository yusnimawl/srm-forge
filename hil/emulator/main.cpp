// Teensy 4.1 motor emulator. Answers HIL_HELLO over USB serial.
#include <Arduino.h>
extern "C" {
#include "hil_hello.h"
}

static hil_hello_t link_state;

void setup() { Serial.begin(115200); }

void loop() {
    uint8_t out[HIL_FRAME_MAX(sizeof(hil_build_info_t))];
    while (Serial.available()) {
        size_t n = hil_hello_feed(&link_state, 1, (uint8_t)Serial.read(), out);
        if (n) Serial.write(out, n);
    }
}
