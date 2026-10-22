import type { components } from "@/api/schema"
import { decode } from "@/lib/fieldWire"

export type Scenario = components["schemas"]["Scenario"]
export type ControlSummary = {
  mean_torque: number | null
  ripple_pct: number | null
  i_rms: number[]
  copper_loss: number | null
  power_in: number | null
  power_mech: number | null
  beyond_map_fraction: number | null
  roundtrip_error: number | null
}
export type ControlMeta = {
  summary: ControlSummary
  scenario: Scenario
  controller: string
  n_phases: number
}
export type Channel = { t: Float32Array; y: Float32Array }

/** Upper bound on duration / dt, as on the server (`srmsil.scenario.MAX_STEPS`). */
export const MAX_STEPS = 50_000_000

export const rpmToRadS = (rpm: number) => (rpm * 2 * Math.PI) / 60
export const radSToRpm = (w: number) => (w * 60) / (2 * Math.PI)

/** The channels of a control response (`t.<name>` / `y.<name>` pairs, e.g. `i.0`, `adc_i.0`) and its meta. */
export function scopesFromWire(buf: ArrayBuffer): { meta: ControlMeta; channels: Record<string, Channel> } {
  const { meta, arrays } = decode(buf)
  const channels: Record<string, Channel> = {}
  for (const key of Object.keys(arrays)) {
    if (!key.startsWith("t.")) continue
    const name = key.slice(2)
    const y = arrays[`y.${name}`]
    if (y) channels[name] = { t: arrays[key].data as Float32Array, y: y.data as Float32Array }
  }
  return { meta, channels }
}

/** The ISR rate (Hz) a controller starts with: the hysteresis band is only tight at a fast ISR. */
export const defaultIsrHz = (controller: string) => (controller === "hysteresis" ? 50_000 : null)

/** A scenario that shows something on the first run: 30 % of the case's peak torque at its base speed. */
export function defaultScenario(busVoltage?: number | null, peakTorque?: number | null, baseSpeedRpm?: number | null): Scenario {
  return {
    mode: "fixed",
    speed_rpm: baseSpeedRpm && baseSpeedRpm > 0 ? baseSpeedRpm : 1000,
    duration: 0.02,
    dt: 0.5e-6,
    command_mode: "torque",
    command_value: peakTorque && peakTorque > 0 ? +(0.3 * peakTorque).toPrecision(2) : 0,
    inertia: 1e-3,
    friction: 0,
    load: 0,
    load_step: 0,
    load_step_time: 0,
    theta0: 0,
    bus_voltage: busVoltage && busVoltage > 0 ? busVoltage : null,
    pwm_hz: 20000,
    isr_hz: null,
    compute_delay: null,
    seed: 0,
    params: {},
    param_steps: [],
    controller_clock: 1,
    converter: { v_switch: 1, v_diode: 1, dead_time: 0.5e-6, turn_on_delay: 0.1e-6, turn_off_delay: 0.2e-6 },
    sensors: {
      encoder_cpr: 4096, encoder_offset: 0, encoder_ecc_amp: 0, encoder_ecc_harmonic: 1, resolver: false,
      resolver_pole_pairs: 1, resolver_bits: 12, resolver_gain_mismatch: 0, resolver_phase_error: 0, delay: 0,
    },
    adc: {
      bits: 12, full_scale: null, offset_counts: 0, offset_error: 0, gain_error: 0, noise: 0, rc_tau: 0,
      volt_full_scale: null, volt_rc_tau: 1e-5,
    },
  }
}

/** The limits the server enforces on a scenario, keyed by field path; empty when it is acceptable. */
export function scenarioErrors(s: Scenario): Record<string, string> {
  const e: Record<string, string> = {}
  const num = (key: string, v: number | null | undefined, min: number, strict = false) => {
    if (v == null) return
    if (!Number.isFinite(v) || (strict ? v <= min : v < min)) e[key] = strict ? `Enter a value above ${min}.` : `Enter a value of at least ${min}.`
  }
  num("duration", s.duration, 0, true)
  num("dt", s.dt, 0, true)
  num("inertia", s.inertia, 0, true)
  num("pwm_hz", s.pwm_hz, 0, true)
  num("isr_hz", s.isr_hz, 0, true)
  num("bus_voltage", s.bus_voltage, 0, true)
  num("friction", s.friction, 0)
  num("load_step_time", s.load_step_time, 0)
  num("compute_delay", s.compute_delay, 0)
  for (const k of ["speed_rpm", "command_value", "load", "load_step", "theta0"] as const)
    if (!Number.isFinite(s[k])) e[k] = "Enter a number."
  if (!e.duration && !e.dt) {
    const n = Math.round(s.duration / s.dt)
    if (n < 1) e.duration = "Shorter than one time step."
    else if (n > MAX_STEPS) e.duration = `${n.toLocaleString("en-US")} steps (duration / dt) exceed ${MAX_STEPS.toLocaleString("en-US")}; shorten the run or raise dt.`
    if (!e.pwm_hz && s.pwm_hz * s.dt > 1) e.pwm_hz = "Must not exceed 1 / dt."
    if (!e.isr_hz && s.isr_hz != null && s.isr_hz * s.dt > 1) e.isr_hz = "Must not exceed 1 / dt."
  }
  const adc = s.adc ?? defaultScenario().adc
  const bits = adc.bits ?? 12
  if (!Number.isInteger(bits) || bits < 1 || bits > 16) e["adc.bits"] = "Whole number from 1 to 16."
  else if (!Number.isInteger(adc.offset_counts ?? 0) || (adc.offset_counts ?? 0) < 0) e["adc.offset_counts"] = "Whole number, 0 or more."
  else if ((adc.offset_counts ?? 0) > 2 ** bits - 1) e["adc.offset_counts"] = `At most ${2 ** bits - 1}.`
  num("adc.full_scale", adc.full_scale, 0, true)
  num("adc.noise", adc.noise, 0)
  num("adc.rc_tau", adc.rc_tau, 0)
  for (const k of ["v_switch", "v_diode", "dead_time", "turn_on_delay", "turn_off_delay"] as const) num(`converter.${k}`, s.converter?.[k], 0)
  const cpr = s.sensors?.encoder_cpr
  if (cpr != null && (!Number.isInteger(cpr) || cpr < 0)) e["sensors.encoder_cpr"] = "Whole number, 0 or more."
  return e
}
