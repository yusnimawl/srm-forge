# Nucleo-H723ZG controller driver

The owner's controller C (`srm_ctrl.h`) runs unchanged on the Nucleo behind `srm_hal_t` (`srm_hal.h`). This driver is
the starting point for the motor controller board (spec D11, §14). Pins: `docs/r8b-hil-wiring.md`.

| File | Contents |
|---|---|
| `srm_hal_stm32.[ch]` | `srm_hal_stm32_init` (fills `srm_hal_t` from the generated `hil_config.h`), sample trigger, `ctrl_isr` scheduling and timing, RUN/READY, `micros` (TIM2), `ctrl_slow` (TIM6, 1 kHz), start/stop, statistics |
| `pwm_ahb.c`, `pwm_compare.[ch]` | TIM1 (upper A-D, PE9/11/13/14) master, TIM8 (lower A-D, PC6-9) slave; `ahb_compare` is portable and tested on the host (`tests/hil/test_hil_pwm_compare.py`) |
| `sense_ad7606.c` | `current_sense = ad7606`: CONVST PD15, BUSY PF3, SPI1 (PA5/PA6, CS PD14) by DMA |
| `sense_internal.c` | `current_sense = internal`: ADC1 + ADC2 dual simultaneous on PA3/PB1/PC0/PA4 by DMA |
| `pos_encoder.c` | TIM4 x4 encoder (PD12/PD13), index Z on PG14 |
| `pos_ad2s1210.c` | AD2S1210 on SPI3 (PC10/11/12), WR/FSYNC PD2, SAMPLE PG2, A0 PG3, A1 PD7 |
| `link.c` | PC link: USART3 (ST-LINK virtual COM port) 921600 baud, `hil_proto.h` frames, DMA both ways |
| `main.c` | clocks (8 MHz bypass from the ST-LINK, 400 MHz core), caches, init, main loop |

## Timing

- PWM: both timers count 0..ARR..0 at 200 MHz, ARR = 200 MHz / (2 pwm_hz), PWM mode 1 with compare preload, no dead
  time, outputs idle low (MOE = 0, OSSI = 1). The update event is at the counter underflow, the centre of the
  on-pulses, as the SIL's sampling instant; `isr_hz` may be 2 x `pwm_hz` or `pwm_hz / k`.
- Sample chain per trigger (TIM1 update, priority 1): `ad7606` CONVST pulse, BUSY falling, 128-bit SPI1 read;
  `internal` TRGO2 starts the ADCs in hardware; `ad2s1210` SAMPLE pulse and an SPI3 read 2 us later. `ctrl_isr`
  (priority 3) runs when every source has its data; its compare values take effect at the next update.
- Overrun: a trigger that finds `ctrl_isr` still running, or the previous chain unfinished (restarted). Three triggers
  in a row with an unfinished chain stop the run ("stall").

## Run control and safety

- `HIL_START`: refused unless the setup is valid, the timers update at the underflow, PA5 is an input (`internal`),
  the AD2S1210 control register reads back (`ad2s1210`, `both`), and READY (PD4, pulled down) is high. Then
  `ctrl_init`, the last `HIL_COMMAND`, RUN (PD6) high, outputs on.
- READY falling (EXTI4, priority 0) or READY low at a trigger: MOE cleared and every compare 0 at once, RUN low,
  `HIL_ERROR` with the reason, live state bit `READY_STOP`.
- `ctrl_param` (from `HIL_PARAM_SET`, replied with its status 0 / -1 / -2) and `ctrl_command` run in the main loop with
  the `ctrl_isr` priority masked.

## Live statistics (`HIL_LIVE_CTRL`, every 50 ms)

ISR time mean (window) and maximum (since start) from the DWT cycle counter, overruns since start, the last command,
RMS of the sampled phase currents, the mean trigger-to-`ctrl_isr` time, and the state bits (`HIL_CTRL_*`: running,
READY high, READY stop, stall stop, encoder index seen).

## Build

`srmsil.hil.build.build_and_flash` (or CI, `.github/workflows/hil.yml`) generates `hil_config.h` with
`srmsil.hil.config.write_hil_config`: modes, `pwm_hz`, `isr_hz`, bus voltage, the ADC scales of the sensing chain
(`sensor_chain`), encoder CPR and resolver bits. The firmware is built with the hard-float ABI at -O2.
`HIL_SPI_MBR` (SPI clock 200 MHz / 2^(MBR+1), default 12.5 MHz) and `HIL_RDC_READ_DELAY_US` can be overridden with
build flags.
