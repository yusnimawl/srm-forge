import { useEffect, useState } from "react"
import { api, ApiError } from "@/api/client"
import type { components } from "@/api/schema"
import { scopesFromWire, type Channel, type ControlMeta, type Scenario } from "@/lib/control"
import { errorMessage } from "@/lib/errorMessage"

export type HilModes = components["schemas"]["HilModes"]
export type HilSession = components["schemas"]["HilSessionOut"]
export type HilParamReply = components["schemas"]["HilParamOut"]
export type HilCaptureOut = components["schemas"]["HilCaptureOut"]
export type HilComparison = components["schemas"]["ComparisonOut"]

/** `srmsil.hil.proto.LiveEmu` as `srmweb.hil.HilManager.poll` serialises it (a non-finite number is null). */
export type HilLiveEmu = {
  step: number
  mean_torque: number | null
  ripple_pct: number | null
  i_rms: (number | null)[]
  speed_rpm: number | null
  step_mean_us: number | null
  step_max_us: number | null
  overruns: number
  dropped: number
  edge_jitter_ns: number | null
  latency_us: number | null
  temp_c: number | null
  trigger_hz: number | null
}

/** `srmsil.hil.proto.LiveCtrl`, serialised the same way. */
export type HilLiveCtrl = {
  isr_mean_us: number | null
  isr_max_us: number | null
  isr_overruns: number
  command: number | null
  i_meas: (number | null)[]
  sample_us: number | null
  tx_dropped: number
  state: number
}

/** The payload of the `live` event of `GET /api/hil/session/events`, the dict `HilManager.poll` returns; it is not in
 *  the OpenAPI schema. */
export type HilLive = { session: HilSession; emu: HilLiveEmu | null; ctrl: HilLiveCtrl | null }

export type HilCaptureMeta = ControlMeta & { compared: boolean }
export type HilFlashResult = components["schemas"]["HilFlashResultOut"]

export const LOOPBACK_TEXT = "HIL needs the server on this computer (loopback)"

/** The emulator step in us (`srmsil.hil.proto.EMU_DT`); the capture route takes 100 to 200 000 steps. */
export const EMU_STEP_US = 6
export const MIN_CAPTURE_MS = (100 * EMU_STEP_US) / 1000
export const MAX_CAPTURE_MS = (200_000 * EMU_STEP_US) / 1000

/** The message of a failed HIL request: the loopback text for a 403, the server's text for a 409 or a 422. */
export function hilErrorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return LOOPBACK_TEXT
    if (Array.isArray(e.detail)) return e.detail.map((i) => `${i.loc.filter((p) => p !== "body").join(".")}: ${i.msg}`).join("; ")
  }
  return errorMessage(e)
}

/** What a `ctrl_param` status means: 0 applied, -2 refused because the controller is running, -1 unknown. */
export function paramStatusText(status: number): string {
  if (status === 0) return "applied"
  if (status === -2) return "refused (not live)"
  if (status === -1) return "unknown"
  return "refused"
}

/** Overruns and drops of a live window; any of them makes the numbers unreliable. `txBase` is the controller's
 *  `tx_dropped` before the run started: the counter runs since boot, so only the increase counts. */
export function liveProblems(live: HilLive, txBase = 0): string[] {
  const out: string[] = []
  const { emu, ctrl } = live
  if (emu?.overruns) out.push(`${emu.overruns} emulator step overruns`)
  if (emu?.dropped) out.push(`${emu.dropped} dropped samples`)
  if (ctrl?.isr_overruns) out.push(`${ctrl.isr_overruns} ISR overruns`)
  if (ctrl && ctrl.tx_dropped > txBase) out.push(`${ctrl.tx_dropped - txBase} frames the controller could not send`)
  return out
}

/** An emulator step max above this share of the step is a warning (`srmsil.hil.session.STEP_WARN_FRACTION`). */
export const STEP_WARN_FRACTION = 0.8

/** Warnings of a live window; unlike `liveProblems` they do not make a run invalid. */
export function liveWarnings(live: HilLive): string[] {
  const max = live.emu?.step_max_us
  if (max == null || !(max > STEP_WARN_FRACTION * EMU_STEP_US)) return []
  return [`emulator step max ${max.toFixed(2)} µs is ${Math.round((100 * max) / EMU_STEP_US)} % of the ${EMU_STEP_US} µs step (warning above ${100 * STEP_WARN_FRACTION} %)`]
}

/** Parts per million that a measured ratio is off its nominal 1. */
export const ppmOff = (ratio: number) => (ratio - 1) * 1e6

/** The controller clock from the emulator's trigger rate against the session's nominal ISR rate. */
export function livePpm(live: HilLive): number | null {
  const hz = live.emu?.trigger_hz
  const isr = live.session.scenario.isr_hz ?? live.session.scenario.pwm_hz
  return hz != null && isr > 0 ? ppmOff(hz / isr) : null
}

/** Emulator steps for a capture of `ms` milliseconds, or null when the length is not accepted. */
export function captureSteps(ms: number): number | null {
  return Number.isFinite(ms) && ms >= MIN_CAPTURE_MS && ms <= MAX_CAPTURE_MS ? Math.round((ms * 1000) / EMU_STEP_US) : null
}

/** A capture's traces (`GET /api/hil/captures/{id}`): the HIL channels, and the matched SIL run's under `sil.` once compared. */
export function captureFromWire(buf: ArrayBuffer): { meta: HilCaptureMeta; channels: Record<string, Channel>; overlay: Record<string, Channel> } {
  const { meta, channels: all } = scopesFromWire(buf)
  const channels: Record<string, Channel> = {}
  const overlay: Record<string, Channel> = {}
  for (const [k, v] of Object.entries(all)) (k.startsWith("sil.") ? overlay : channels)[k] = v
  return { meta: meta as HilCaptureMeta, channels, overlay }
}

export type HilSetup = { controller: string; scenario: Scenario; modes: HilModes }
const post = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })

export const hilFlash = (caseId: string, setup: HilSetup) => post<{ job_id: string }>(`/api/cases/${caseId}/hil/flash`, setup)
export const hilOpen = (caseId: string, setup: HilSetup) => post<HilSession>("/api/hil/session", { case_id: caseId, ...setup })
export const hilClose = () => api<void>("/api/hil/session", { method: "DELETE" })
export const hilStart = () => post<HilSession>("/api/hil/session/start")
export const hilStop = () => post<HilSession>("/api/hil/session/stop")
export const hilCommand = (mode: "torque" | "speed", value: number) => post<HilSession>("/api/hil/session/command", { mode, value })
export const hilFlashResult = (jobId: string) => api<HilFlashResult>(`/api/jobs/${jobId}/hil-flash`)
export const hilParam = (name: string, value: number) => post<HilParamReply>("/api/hil/session/param", { name, value })
export const hilCapture = (nSteps: number) => post<HilCaptureOut>("/api/hil/session/capture", { n_steps: nSteps })
export const hilCompare = (id: string) => api<HilComparison>(`/api/hil/captures/${id}/compare`)

export async function hilCaptureTraces(id: string, nPx = 1500) {
  const res = await fetch(`/api/hil/captures/${id}?n_px=${nPx}`, { credentials: "same-origin" })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? res.statusText, body)
  }
  return captureFromWire(await res.arrayBuffer())
}

/** The live event stream of the open session. A new `epoch` reconnects (the stream of a closed session ends, and a
 *  stream opened with no session fails once). `live` is the newest event, `ended` is true after the server closed the
 *  session, and `lost` is true when the connection broke after events had arrived (the session may still be open). */
export function useHilEvents(epoch: number): { live: HilLive | null; ended: boolean; lost: boolean } {
  const [live, setLive] = useState<HilLive | null>(null)
  const [ended, setEnded] = useState(false)
  const [lost, setLost] = useState(false)
  useEffect(() => {
    const es = new EventSource("/api/hil/session/events")
    let seen = false
    es.addEventListener("live", (e) => {
      seen = true
      setLive(JSON.parse((e as MessageEvent).data) as HilLive)
      setEnded(false)
      setLost(false)
    })
    es.addEventListener("end", () => {
      setLive(null)
      setEnded(true)
      es.close()
    })
    // readyState CLOSED (2): the browser gave up, as it does for a 409 when no session is open.
    es.onerror = () => {
      if (es.readyState !== 2) return
      setLive(null)
      if (seen) setLost(true)
    }
    return () => es.close()
  }, [epoch])
  return { live, ended, lost }
}
