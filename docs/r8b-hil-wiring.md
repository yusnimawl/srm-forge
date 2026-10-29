# R8b HIL wiring: NUCLEO-H723ZG (controller) <-> Teensy 4.1 (motor emulator)

Both boards are 3.3 V logic. Teensy 4.1 pins are not 5 V tolerant (PJRC). Nucleo: JP5 on 3V3 (VDD_MCU = 3.3 V); default solder bridges, no SB change needed for anything below.

Nucleo connector labels are from UM2407 Rev 4 (Oct 2023), Tables 18-22 ("NUCLEO-H723ZG, NUCLEO-H743ZI2, and NUCLEO-H753ZI pin assignments"). AF numbers are from DS13313 Rev 5 Table 8. Teensy port.bit is the `CORE_PINn_PORTREG`/`CORE_PINn_BIT` of `cores/teensy4/core_pins.h` (ARDUINO_TEENSY41); GPIO6/7/8/9 are the fast aliases of GPIO1/2/3/4.

**Series resistor:** put 330 Ω in series on the shared SCK wire (Nucleo D13/PA5 <-> Teensy 13). In DAC mode the Teensy drives it and the Nucleo pin must be an input; the resistor limits the current if a firmware fault makes both drive it. The firmware mode handshake (spec §5.4) is the primary guard.

**Minimum wiring for the first runs (no extra parts):** gates, encoder, the AD7606 group, the AD2S1210 group, RUN, READY and two GND wires. The DAC rows are needed only for `current_sense = internal`.

## 1. Wiring table

| Signal | Direction | Nucleo STM32 pin | Nucleo connector (Zio / Morpho) | Teensy pin | Teensy GPIO port.bit | Mode(s) in use | Notes |
|---|---|---|---|---|---|---|---|
| Gate A upper | Nucleo -> Teensy | PE9 (TIM1_CH1, AF1) | Zio D6 = CN10-4 / CN12-52 | 14 | GPIO6.18 (GPIO1.18) | all | SB28 ON / SB70 OFF default puts PE9 on CN10-4. Do not use CN9-15 (D71), not connected by default. |
| Gate B upper | Nucleo -> Teensy | PE11 (TIM1_CH2, AF1) | Zio D5 = CN10-6 / CN12-56 | 15 | GPIO6.19 | all | |
| Gate C upper | Nucleo -> Teensy | PE13 (TIM1_CH3, AF1) | Zio D3 = CN10-10 / CN12-55 | 16 | GPIO6.23 | all | |
| Gate D upper | Nucleo -> Teensy | PE14 (TIM1_CH4, AF1) | Zio D4 = CN10-8 / CN12-51 | 17 | GPIO6.22 | all | Zio name "I/O", TIM1_CH4 is AF1 per DS. |
| Gate A lower | Nucleo -> Teensy | PC6 (TIM8_CH1, AF3) | Zio D16 = CN7-1 / CN12-4 | 18 | GPIO6.17 | all | Teensy 18 is also Wire SDA (unused). |
| Gate B lower | Nucleo -> Teensy | PC7 (TIM8_CH2, AF3) | Zio D21 = CN7-11 / CN12-19 | 19 | GPIO6.16 | all | Teensy 19 is also Wire SCL (unused). |
| Gate C lower | Nucleo -> Teensy | PC8 (TIM8_CH3, AF3) | Zio D43 = CN8-2 / CN12-2 | 20 | GPIO6.26 | all | SB14 ON (default) also routes PC8 to CN12; harmless. No SD card on board. |
| Gate D lower | Nucleo -> Teensy | PC9 (TIM8_CH4, AF3) | Zio D44 = CN8-4 / CN12-1 | 21 | GPIO6.27 | all | SB15 ON (default) also routes PC9 to CN12. |
| Encoder A | Teensy -> Nucleo | PD12 (TIM4_CH1, AF2) | Zio D29 = CN10-21 / CN12-43 | 2 | GPIO9.4 (GPIO4.4) | all | Zio label "QSPI_BK1_IO1" is only a label; UM2407 lists no QSPI memory. |
| Encoder B | Teensy -> Nucleo | PD13 (TIM4_CH2, AF2) | Zio D28 = CN10-19 / CN12-41 | 3 | GPIO9.5 | all | |
| Encoder Z | Teensy -> Nucleo | PG14 (GPIO, EXTI14) | Zio D2 = CN10-12 / CN12-61 | 4 | GPIO9.6 | all | EXTI line 14; no other EXTI user on line 14. |
| AD7606 SCLK | Nucleo -> Teensy (ADC mode); Nucleo pin high-Z (DAC mode) | PA5 (SPI1_SCK, AF5) | Zio D13 = CN7-10 / CN12-11 | 13 (LPSPI4 SCK) | GPIO7.3 | ADC mode: Teensy LPSPI4 slave. DAC mode: Teensy LPSPI4 master drives this wire | In DAC mode set PA5 to GPIO input (or analog). LD1 is on PB0 by default (SB39 ON, SB47 OFF), so no LED on PA5. Teensy pin 13 carries the orange LED. |
| AD7606 DOUTA | Teensy -> Nucleo | PA6 (SPI1_MISO, AF5) | Zio D12 = CN7-12 / CN12-13 | 11 (LPSPI4 SDO) | GPIO7.2 | ADC mode: data to Nucleo. DAC mode: same wire is the DAC SDI | PA6 stays an input in both modes. Set LPSPI4 CFGR1.OUTCFG=1 in slave mode so SDO tri-states while CS is high. |
| AD7606 CS | Nucleo -> Teensy | PD14 (GPIO out) | Zio D10 = CN7-16 / CN12-46 | 10 (LPSPI4 PCS0) | GPIO7.0 | ADC mode | Keep PD14 high in DAC mode; Teensy pin 10 stays an input. |
| AD7606 CONVST | Nucleo -> Teensy | PD15 (GPIO out) | Zio D9 = CN7-18 / CN12-48 | 5 | GPIO9.8 | ADC mode | |
| AD7606 BUSY | Teensy -> Nucleo | PF3 (GPIO in, EXTI3) | Zio D8 = CN7-20 / CN12-58 | 6 | GPIO7.10 | ADC mode | EXTI line 3. |
| SPI1 MOSI | - | (PB5, not wired) | Zio D11 = CN7-14 | - | - | - | Not needed (AD7606 serial has no data input). Run SPI1 as RX-only master, or full-duplex with no MOSI GPIO configured. |
| AD2S1210 SCLK | Nucleo -> Teensy | PC10 (SPI3_SCK, AF6) | Zio D45 = CN8-6 / CN11-1 | 27 (LPSPI3 SCK) | GPIO6.31 | resolver mode | |
| AD2S1210 SDI (MOSI) | Nucleo -> Teensy | PC12 (SPI3_MOSI, AF6) | Zio D47 = CN8-10 / CN11-3 | 1 (LPSPI3 SDI) | GPIO6.2 | resolver mode | Teensy 1 is also Serial1 TX: leave Serial1 unused. |
| AD2S1210 SDO (MISO) | Teensy -> Nucleo | PC11 (SPI3_MISO, AF6) | Zio D46 = CN8-8 / CN11-2 | 26 (LPSPI3 SDO) | GPIO6.30 | resolver mode | |
| AD2S1210 WR/FSYNC (CS) | Nucleo -> Teensy | PD2 (GPIO out) | Zio D48 = CN8-12 / CN11-4 | 0 (LPSPI3 PCS0) | GPIO6.3 | resolver mode | Teensy 0 is also Serial1 RX: leave Serial1 unused. |
| AD2S1210 SAMPLE | Nucleo -> Teensy | PG2 (GPIO out) | Zio D49 = CN8-14 / CN11-42 | 9 | GPIO7.11 | resolver mode | |
| AD2S1210 A0 | Nucleo -> Teensy | PG3 (GPIO out) | Zio D50 = CN8-16 / CN11-44 | 22 | GPIO6.24 | resolver mode | |
| AD2S1210 A1 | Nucleo -> Teensy | PD7 (GPIO out) | Zio D51 = CN9-2 / CN11-45 | 23 | GPIO6.25 | resolver mode | |
| RUN | Nucleo -> Teensy | PD6 (GPIO out) | Zio D52 = CN9-4 / CN11-43 | 7 | GPIO7.17 | all | |
| READY/FAULT | Teensy -> Nucleo | PD4 (GPIO in, EXTI4) | Zio D54 = CN9-8 / CN11-39 | 8 | GPIO7.16 | all | EXTI line 4. |
| Current A (analog) | DAC1 VOUTA -> Nucleo | PA3 (ADC12_INP15) | Zio A0 = CN9-1 / CN12-37 | - | - | analog current mode | ADC1 rank 1. |
| Current B (analog) | DAC2 VOUTA -> Nucleo | PB1 (ADC12_INP5) | Zio A3 = CN9-7 / CN12-24 | - | - | analog current mode | ADC2 rank 1 (simultaneous with A). |
| Current C (analog) | DAC1 VOUTB -> Nucleo | PC0 (ADC123_INP10) | Zio A1 = CN9-3 / CN11-38 | - | - | analog current mode | ADC1 rank 2. |
| Current D (analog) | DAC2 VOUTB -> Nucleo | PA4 (ADC12_INP18) | Zio D24 = CN7-17 / CN11-32 | - | - | analog current mode | ADC2 rank 2. Zio label SPI_B_NSS is unused. |
| DAC SCK | Teensy -> DACs | (shares PA5 wire) | - | 13 | GPIO7.3 | DAC mode | Same wire as AD7606 SCLK. |
| DAC SDI | Teensy -> DACs | (shares PA6 wire) | - | 11 | GPIO7.2 | DAC mode | Same wire as AD7606 DOUTA. |
| DAC CS 1 | Teensy -> DAC | - | - | 24 | GPIO6.12 | DAC mode | |
| DAC CS 2 | Teensy -> DAC | - | - | 25 | GPIO6.13 | DAC mode | |
| DAC CS 3 | Teensy -> DAC | - | - | 28 | GPIO8.18 | DAC mode | Not needed with two MCP4922 (CS 1, 2 only); needed with four MCP4921. |
| DAC CS 4 | Teensy -> DAC | - | - | 29 | GPIO9.31 | DAC mode | as above |
| DAC LDAC | Teensy -> DACs | - | - | 30 | GPIO8.23 | DAC mode | |

DACs: supply and VREF from 3.3 V so VOUT never exceeds the Nucleo VDDA (3.3 V).

ADC dual simultaneous mode: ADC1 sequence PA3, PC0; ADC2 sequence PB1, PA4. All four are ADC1/ADC2 inputs (DS13313 Table 7).

EXTI lines used on the Nucleo: 3 (PF3 BUSY), 4 (PD4 READY/FAULT), 14 (PG14 Z). All distinct, and none is 13 (B1 on PC13).

Teensy interrupts: PJRC says "All digital pins can detect changes" (attachInterrupt), so 4-9, 0, 10 and the gate inputs can all interrupt.

## 2. GND connections

Use at least two ground wires, one beside the SPI group and one beside the gate group:

- Nucleo GND: CN7-8, CN8-11, CN8-13, CN9-12, CN9-23, CN10-5, CN10-17, CN10-22, CN10-27 (Zio); CN11-8/19/20/22/49/59, CN12-9/20/39/54/63 (Morpho).
- Teensy 4.1 GND: the GND pad beside pin 0, and the GND between VIN and 3.3V (PJRC pinout card).
- Suggested: Nucleo CN10-5 <-> Teensy GND (beside pin 0); Nucleo CN7-8 <-> Teensy GND (VIN/3.3V side); DAC ground to the Nucleo AGND (CN10-3), DAC supply from Nucleo 3V3 (CN8-7).
- Power each board from its own USB. Do not connect 3V3 to 3V3 or 5V to VIN between the boards.

## 3. Changes to the candidates and why

1. SPI #2 is SPI3 on PC10/PC11/PC12 (Zio CN8 D45-D47), not SPI2. SPI2 needs PB13 (Ethernet RMII TXD1 via JP6, ON by default) or PB14 (LD3). The Zio SPI_B pins (PB3/PB4/PB5) were also rejected: PB3 is SWO to the ST-LINK (SB32 ON by default), and PB5 is also D11 (SB35 ON by default).
2. ADC: A2 (PC3) is replaced by PA4 (D24). On LQFP144 the package pin is PC3_C, and ADC12_INP13 needs the SYSCFG analog switch closed (DS13313 Table 7, note 1). A4 (PC2) is also a `_C` pin, and A5 (PF10) is ADC3 only, so neither is usable for ADC1/ADC2 dual mode. The pins chosen are PA3, PC0, PB1 and PA4, all plain ADC12 inputs.
3. SPI1 MOSI is not wired, because the AD7606 has no serial data input. This keeps PB5 free and avoids PA7 (Ethernet CRS_DV, SB31 ON by default).
4. The GPIO picks were not given in the request and are chosen here: AD7606 CONVST PD15 (D9), BUSY PF3 (D8), AD2S1210 CS PD2 (D48), SAMPLE PG2 (D49), A0 PG3 (D50), A1 PD7 (D51), RUN PD6 (D52), READY/FAULT PD4 (D54), encoder Z PG14 (D2). All are on Zio, need no SB change, and keep the EXTI lines distinct.
5. All the other candidates were confirmed unchanged: TIM1 PE9/PE11/PE13/PE14, TIM8 PC6-PC9, TIM4 PD12/PD13, SPI1 PA5/PA6 with CS PD14, the Teensy gate pins 14-21 (all GPIO1/6), LPSPI4 10-13, LPSPI3 0/1/26/27, and Teensy pins 2-9, 22-25 and 28-30.
6. DAC mode: Nucleo PA5 must be switched to an input, because both boards drive the same SCK wire. PA6 is an input in both modes. The Teensy needs LPSPI4 OUTCFG=1 in slave mode so that its SDO releases the shared wire while CS is high.

## 4. Sources

- UM2407 Rev 4, STM32H7 Nucleo-144 boards (MB1364) (archived ST copy): https://web.archive.org/web/2025/https://www.st.com/resource/en/user_manual/um2407-stm32h7-nucleo144-boards-mb1364-stmicroelectronics.pdf (original: https://www.st.com/resource/en/user_manual/um2407-stm32h7-nucleo144-boards-mb1364-stmicroelectronics.pdf; Rev 6 is at https://st.com/resource/en/user_manual/um2407-stm32h7-nucleo144-boards-mb1363-stmicroelectronics.pdf)
- DS13313 Rev 5, STM32H723xE/G datasheet (archived ST copy): https://web.archive.org/web/2025/https://www.st.com/resource/en/datasheet/stm32h723zg.pdf
- PJRC Teensy 4.1 page: https://www.pjrc.com/store/teensy41.html
- Teensy core pin map: https://raw.githubusercontent.com/PaulStoffregen/cores/master/teensy4/core_pins.h
- Teensy SPI pin tables (LPSPI4, LPSPI3): https://raw.githubusercontent.com/PaulStoffregen/SPI/master/SPI.cpp
- Teensy Serial1 pins: https://raw.githubusercontent.com/PaulStoffregen/cores/master/teensy4/HardwareSerial1.cpp
- Teensy SPI and LED pin defines: https://raw.githubusercontent.com/PaulStoffregen/cores/master/teensy4/pins_arduino.h
- LPSPI OUTCFG values (same LPSPI IP, MCX part): https://docs.embassy.dev/nxp-pac/git/mcxa577/lpspi/enum.Outcfg.html

## 5. UNVERIFIED

1. **LPSPI SDO tri-state (OUTCFG=1).** The values come from an NXP MCX PAC that uses the same LPSPI IP, not from IMXRT1060RM. The same goes for the claim that SDO is an output and SDI an input in both master and slave mode when PINCFG=0 (the reset value). Check both in the IMXRT1060RM LPSPI CFGR1 description before relying on the shared MISO/DAC-SDI wire.
2. **UM2407 revision.** I read Rev 4 (Oct 2023, archived copy) because st.com timed out. Rev 6 (Apr 2026) exists. The solder-bridge defaults were taken from the bold entries in Rev 4 Table 14.
3. **Your board's MB1364 revision and SB state.** I did not inspect your board. Check the sticker and that SB28, SB39, SB14/SB15 and SB32 match the defaults.
4. **Teensy GND pad positions.** These come from the PJRC pinout card layout and were not checked against text. Confirm them on the card printed with the board.
5. **Pin 13 LED load on SCK.** PJRC confirms the LED is on pin 13. Its effect on SCK edges at high SPI clock rates was not checked. Scope it at the clock rate you will use.
6. **No QSPI memory behind D28/D29 (PD13/PD12).** UM2407 lists no QSPI memory, only Zio labels, but no schematic was checked.
