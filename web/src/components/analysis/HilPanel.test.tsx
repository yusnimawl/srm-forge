// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("./ControlScopes", () => ({ default: ({ overlay }: { overlay?: object }) => <div data-testid="scopes" data-overlay={Object.keys(overlay ?? {}).join(",")} /> }))

import HilPanel from "./HilPanel"
import { defaultScenario } from "@/lib/control"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

class FakeEventSource {
  static all: FakeEventSource[] = []
  listeners: Record<string, (e: Event) => void> = {}
  closed = false
  readyState = 1
  onerror: (() => void) | null = null
  url: string
  constructor(url: string) { this.url = url; FakeEventSource.all.push(this) }
  addEventListener(n: string, f: (e: Event) => void) { this.listeners[n] = f }
  close() { this.closed = true }
  emit(n: string, data: unknown) { this.listeners[n](new MessageEvent(n, { data: JSON.stringify(data) })) }
}
const stream = () => FakeEventSource.all[FakeEventSource.all.length - 1]

/** Packs arrays like srmweb/frames.py: u32 header length, JSON header, 8-byte aligned data. */
function pack(meta: unknown, arrays: Record<string, Float32Array>): ArrayBuffer {
  let offset = 0
  const entries = Object.entries(arrays).map(([name, a]) => {
    const e = { name, dtype: "float32", shape: [a.length], offset }
    offset += Math.ceil(a.byteLength / 8) * 8
    return e
  })
  const head = new TextEncoder().encode(JSON.stringify({ meta, arrays: entries }))
  const buf = new ArrayBuffer(4 + head.length + offset)
  new DataView(buf).setUint32(0, head.length, true)
  new Uint8Array(buf, 4, head.length).set(head)
  entries.forEach((e) => new Uint8Array(buf, 4 + head.length + e.offset, e.shape[0] * 4).set(new Uint8Array(arrays[e.name].buffer)))
  return buf
}

const scenario = defaultScenario(48, 2, 1500)
const SESSION = {
  case_id: "c1", controller: "hysteresis", modes: { current_sense: "ad7606", position: "encoder", dac: "mcp4922x2" },
  scenario, emulator_hash: 255, controller_hash: 4096, running: true,
}
const EMU = {
  step: 1000, mean_torque: 0.61, ripple_pct: 22.5, i_rms: [3.2, 3.1, 0, 0], speed_rpm: 1500, step_mean_us: 3.1, step_max_us: 4.2,
  overruns: 0, dropped: 0, edge_jitter_ns: 20, latency_us: 1.5, temp_c: 41, trigger_hz: 20000.4,
}
const CTRL = { isr_mean_us: 8, isr_max_us: 11, isr_overruns: 0, command: 0.6, i_meas: [3.2, 3.1, 0, 0], sample_us: 1, tx_dropped: 0, state: 3 }
const live = (emu = {}, ctrl = {}) => ({ session: SESSION, emu: { ...EMU, ...emu }, ctrl: { ...CTRL, ...ctrl } })

type Reply = (init?: RequestInit) => Promise<Response>
let routes: Record<string, Reply> = {}
const calls: { url: string; method: string; body: unknown }[] = []
const roots: { unmount: () => void }[] = []

const PARAMS = [{ name: "band", unit: "A", default: "0.05" }]

async function mount(props: Partial<React.ComponentProps<typeof HilPanel>> = {}) {
  vi.stubGlobal("EventSource", FakeEventSource)
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(init.body as string) : undefined })
    const r = routes[`${init?.method ?? "GET"} ${url}`]
    return r ? r(init) : json(200, {})
  })
  const host = document.createElement("div")
  document.body.append(host)
  const root = createRoot(host)
  roots.push(root)
  await act(async () => {
    root.render(<HilPanel caseId="c1" controller="hysteresis" scenario={scenario} params={PARAMS} custom={false} invalid={false} {...props} />)
  })
}

afterEach(async () => {
  await act(async () => { roots.splice(0).forEach((r) => r.unmount()) })
  document.body.innerHTML = ""
  routes = {}
  calls.length = 0
  FakeEventSource.all = []
  vi.unstubAllGlobals()
})

const button = (text: string) => Array.from(document.body.querySelectorAll("button")).find((b) => b.textContent === text) as HTMLButtonElement
const text = () => document.body.textContent ?? ""
const setValue = async (el: HTMLInputElement | HTMLSelectElement, value: string) => {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value)
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }))
  })
}
const blur = (el: HTMLElement) => act(async () => { el.dispatchEvent(new FocusEvent("focusout", { bubbles: true })) })
const emitLive = (data: unknown) => act(async () => { stream().emit("live", data) })

describe("HilPanel", () => {
  it("shows the DAC selector only for internal current sensing", async () => {
    await mount()
    expect(document.getElementById("hil-cs")).not.toBeNull()
    expect(document.getElementById("hil-pos")).not.toBeNull()
    expect(document.getElementById("hil-dac")).toBeNull()
    await setValue(document.getElementById("hil-cs") as HTMLSelectElement, "internal")
    expect(document.getElementById("hil-dac")).not.toBeNull()
    await setValue(document.getElementById("hil-cs") as HTMLSelectElement, "ad7606")
    expect(document.getElementById("hil-dac")).toBeNull()
  })

  it("posts the controller, scenario and modes to Build & Flash and shows the steps", async () => {
    routes["POST /api/cases/c1/hil/flash"] = () => json(201, { job_id: "j7" })
    await mount()
    await setValue(document.getElementById("hil-cs") as HTMLSelectElement, "internal")
    await act(async () => { button("Build & Flash").click() })
    const post = calls.find((c) => c.url === "/api/cases/c1/hil/flash")!
    expect(post.body).toMatchObject({ controller: "hysteresis", modes: { current_sense: "internal", position: "encoder", dac: "mcp4922x2" }, scenario: { speed_rpm: 1500 } })
    const progress = { steps: ["queued", "build", "flash", "saved"], step: "build" }
    await act(async () => { stream().emit("progress", { id: "j7", kind: "hil_flash", status: "running", active: true, progress }) })
    expect(document.querySelector('[aria-label="Job steps"]')).not.toBeNull()
    await act(async () => { stream().emit("end", { id: "j7", kind: "hil_flash", status: "failed", active: false, error: "build failed:\nmain.cpp:3: error", progress }) })
    expect(document.body.querySelector("pre")?.textContent).toContain("main.cpp:3")
    expect((document.querySelector("details") as HTMLDetailsElement).open).toBe(true)
  })

  it("shows the build log, collapsed, after a successful flash and keeps Build & Flash off while it runs", async () => {
    routes["POST /api/cases/c1/hil/flash"] = () => json(201, { job_id: "j7" })
    routes["GET /api/jobs/j7/hil-flash"] = () => json(200, { case_id: "c1", controller: "hysteresis", modes: {}, firmware_hash: 4660, log: "Uploading .pio/build/nucleo\nSUCCESS" })
    await mount()
    await act(async () => { button("Build & Flash").click() })
    const progress = { steps: ["queued", "build", "flash", "saved"], step: "flash" }
    await act(async () => { stream().emit("progress", { id: "j7", kind: "hil_flash", status: "running", active: true, progress }) })
    expect(button("Build & Flash").disabled).toBe(true)
    expect(button("Open session").disabled).toBe(true)
    await act(async () => { stream().emit("end", { id: "j7", kind: "hil_flash", status: "done", active: false, progress: { ...progress, step: "saved" } }) })
    await vi.waitFor(() => expect(document.querySelector("details pre")?.textContent).toContain("SUCCESS"))
    expect((document.querySelector("details") as HTMLDetailsElement).open).toBe(false)
    expect(button("Build & Flash").disabled).toBe(false)
  })

  it("shows a running flash job of the case again after a reload", async () => {
    await mount({ activeFlashId: "j9" })
    expect(stream().url).toBe("/api/jobs/j9/events")
    const progress = { steps: ["queued", "build", "flash", "saved"], step: "build" }
    await act(async () => { stream().emit("progress", { id: "j9", kind: "hil_flash", status: "running", active: true, progress }) })
    expect(document.querySelector('[aria-label="Job steps"]')).not.toBeNull()
    expect(button("Build & Flash").disabled).toBe(true)
  })

  it("shows the server text of a refused open and the loopback text of a 403", async () => {
    routes["POST /api/hil/session"] = () => json(409, { detail: "rig not found: Teensy port None, ST-LINK port None" })
    await mount()
    await act(async () => { button("Open session").click() })
    expect(text()).toContain("rig not found")
    routes["POST /api/hil/session"] = () => json(403, { detail: "the HIL rig runs only when srmweb is bound to a loopback host" })
    await act(async () => { button("Open session").click() })
    expect(text()).toContain("HIL needs the server on this computer (loopback)")
  })

  it("shows the live numbers and the clock offset of an open session", async () => {
    await mount()
    expect(button("Start").disabled).toBe(true)
    await emitLive({ ...live(), session: { ...SESSION, running: false } })
    expect(button("Start").disabled).toBe(false)
    await emitLive(live())
    expect(text()).toContain("0.610 N·m")
    expect(text()).toContain("1500 rpm")
    expect(text()).toContain("+20 ppm")
    expect(text()).not.toContain("invalid")
  })

  it("shows a red invalid chip on an overrun or a drop", async () => {
    await mount()
    await emitLive(live({ overruns: 2 }))
    expect(document.querySelector('[data-testid="hil-invalid"]')).not.toBeNull()
    await emitLive(live({}, { isr_overruns: 0, tx_dropped: 0 }))
    expect(document.querySelector('[data-testid="hil-invalid"]')).toBeNull()
    await emitLive(live({ dropped: 1 }))
    expect(document.querySelector('[data-testid="hil-invalid"]')).not.toBeNull()
  })

  it("shows a step time over 80 % of the step as a warning, not as invalid", async () => {
    await mount()
    await emitLive(live({ step_max_us: 4.8 }))
    expect(document.querySelector('[data-testid="hil-warning"]')).toBeNull()
    await emitLive(live({ step_max_us: 5.04 }))
    expect(document.querySelector('[data-testid="hil-warning"]')?.textContent).toContain("84 % of the 6 µs step")
    expect(document.querySelector('[data-testid="hil-invalid"]')).toBeNull()
  })

  it("counts dropped frames only after the run started", async () => {
    await mount()
    await emitLive({ ...live({}, { tx_dropped: 3 }), session: { ...SESSION, running: false } })
    expect(document.querySelector('[data-testid="hil-invalid"]')).toBeNull()
    await emitLive(live({}, { tx_dropped: 3 }))
    expect(document.querySelector('[data-testid="hil-invalid"]')).toBeNull()
    await emitLive(live({}, { tx_dropped: 4 }))
    expect(document.querySelector('[data-testid="hil-invalid"]')).not.toBeNull()
  })

  it("closes the session view when the connection breaks after events, and reconnects", async () => {
    await mount()
    await act(async () => { stream().readyState = 2; stream().onerror!() })
    expect(text()).not.toContain("The live connection closed")      // never had a session: the quiet 409 case
    await emitLive(live())
    expect(button("Stop").disabled).toBe(false)
    const first = stream()
    await act(async () => { first.readyState = 2; first.onerror!() })
    expect(text()).toContain("No session open")
    expect(button("Stop").disabled).toBe(true)
    expect(button("Start").disabled).toBe(true)
    expect(text()).toContain("The live connection closed")
    await act(async () => { button("Reconnect").click() })
    expect(stream()).not.toBe(first)
    await emitLive(live())
    expect(text()).not.toContain("The live connection closed")
  })

  it("sends a parameter on blur and shows refused (not live) for status -2", async () => {
    routes["POST /api/hil/session/param"] = () => json(200, { status: -2, message: "not changeable while running" })
    await mount()
    await emitLive(live())
    const input = document.getElementById("hil-p-band") as HTMLInputElement
    expect(input.disabled).toBe(false)
    await setValue(input, "0.2")
    await blur(input)
    expect(calls.find((c) => c.url === "/api/hil/session/param")!.body).toEqual({ name: "band", value: 0.2 })
    expect(text()).toContain("refused (not live)")
  })

  it("shows applied, unknown and refused for the other statuses", async () => {
    await mount()
    await emitLive(live())
    const input = document.getElementById("hil-p-band") as HTMLInputElement
    for (const [status, shown] of [[0, "applied"], [-1, "unknown"], [-7, "refused"]] as const) {
      routes["POST /api/hil/session/param"] = () => json(200, { status })
      await setValue(input, String(status + 10))
      await blur(input)
      expect(document.getElementById("hil-p-band-status")?.textContent).toBe(shown)
    }
  })

  it("sends a refused value again but not an applied one", async () => {
    let status = -2
    routes["POST /api/hil/session/param"] = () => json(200, { status })
    await mount()
    await emitLive(live())
    const input = document.getElementById("hil-p-band") as HTMLInputElement
    await setValue(input, "0.2")
    await blur(input)
    await blur(input)
    expect(calls.filter((c) => c.url === "/api/hil/session/param")).toHaveLength(2)
    status = 0
    await blur(input)
    await blur(input)
    expect(calls.filter((c) => c.url === "/api/hil/session/param")).toHaveLength(3)
  })

  it("sends the same value again in a new session", async () => {
    routes["POST /api/hil/session/param"] = () => json(200, { status: 0 })
    await mount()
    await emitLive(live())
    const input = document.getElementById("hil-p-band") as HTMLInputElement
    await setValue(input, "0.2")
    await blur(input)
    await act(async () => { stream().emit("end", {}) })
    await emitLive(live())
    await blur(document.getElementById("hil-p-band")!)
    expect(calls.filter((c) => c.url === "/api/hil/session/param")).toHaveLength(2)
  })

  it("sends the command in the scenario's mode and shows the reply or the error", async () => {
    routes["POST /api/hil/session/command"] = (init) => json(200, { ...SESSION, scenario: { ...scenario, command_value: JSON.parse(init!.body as string).value } })
    await mount()
    expect((document.getElementById("hil-cmd-value") as HTMLInputElement).disabled).toBe(true)
    await emitLive(live())
    const value = document.getElementById("hil-cmd-value") as HTMLInputElement
    expect(value.value).toBe("0.6")
    await setValue(value, "1.2")
    await blur(value)
    expect(calls.find((c) => c.url === "/api/hil/session/command")!.body).toEqual({ mode: "torque", value: 1.2 })
    expect(document.getElementById("hil-cmd-status")?.textContent).toBe("commanded 1.2 N·m")
    await setValue(document.getElementById("hil-cmd-mode") as HTMLSelectElement, "speed")
    routes["POST /api/hil/session/command"] = () => json(409, { detail: "a dynamic run takes no speed command" })
    await setValue(value, "800")
    await blur(value)
    expect(calls.filter((c) => c.url === "/api/hil/session/command").pop()!.body).toEqual({ mode: "speed", value: 800 })
    expect(document.getElementById("hil-cmd-status")?.textContent).toBe("a dynamic run takes no speed command")
  })

  it("has free-form live parameter rows for a custom controller, with the same replies", async () => {
    await mount({ custom: true, params: [] })
    expect(document.getElementById("hil-p-band")).toBeNull()
    await act(async () => { button("Add live parameter").click() })
    await act(async () => { button("Add live parameter").click() })
    expect(document.querySelector('[aria-label="Live parameter 2 name"]')).not.toBeNull()
    await emitLive(live())
    const name1 = document.querySelector('[aria-label="Live parameter 1 name"]') as HTMLInputElement
    const value1 = document.querySelector('[aria-label="Live parameter 1 value"]') as HTMLInputElement
    expect(button("Send").disabled).toBe(true)
    await setValue(name1, "kp")
    await setValue(value1, "2.5")
    routes["POST /api/hil/session/param"] = () => json(200, { status: -2, message: "not changeable while running" })
    await act(async () => { button("Send").click() })
    expect(calls.find((c) => c.url === "/api/hil/session/param")!.body).toEqual({ name: "kp", value: 2.5 })
    expect(document.getElementById("hil-fp-1-status")?.textContent).toBe("refused (not live)")
    routes["POST /api/hil/session/param"] = () => json(200, { status: -1 })
    await act(async () => { button("Send").click() })
    expect(document.getElementById("hil-fp-1-status")?.textContent).toBe("unknown")
    await act(async () => { button("Remove").click() })
    expect(document.querySelector('[aria-label="Live parameter 2 name"]')).toBeNull()
  })

  it("keeps the parameter rows off without a session", async () => {
    await mount()
    expect((document.getElementById("hil-p-band") as HTMLInputElement).disabled).toBe(true)
  })

  const CAPTURE_META = { summary: {}, scenario, controller: "hysteresis", n_phases: 4, compared: true, hil: {} }
  const traces = () => pack(CAPTURE_META, {
    "t.i.0": new Float32Array([0, 1]), "y.i.0": new Float32Array([0, 1]),
    "t.sil.i.0": new Float32Array([0, 1]), "y.sil.i.0": new Float32Array([0, 1]),
  })

  it("shows the invalid chip, the reason and no pass badge for an invalid capture", async () => {
    routes["POST /api/hil/session/capture"] = () => json(201, { capture_id: "abc", valid: false, reason: "overruns 3, ISR overruns 0, dropped 0", clipped: 0 })
    routes["GET /api/hil/captures/abc/compare"] = () => json(200, {
      d_torque_pct: null, d_irms_pct: null, d_ripple_pts: null, passed: false, clock_ratio: null, clock_measured: false, reason: "HIL run not valid: overruns 3",
    })
    await mount()
    await emitLive(live())
    await act(async () => { button("Capture").click() })
    expect(document.querySelector('[data-testid="capture-invalid"]')).not.toBeNull()
    expect(text()).toContain("overruns 3, ISR overruns 0, dropped 0")
    expect(document.querySelector('[data-testid="verdict-pass"]')).toBeNull()
    expect(document.querySelector('[data-testid="verdict-fail"]')).toBeNull()
  })

  it("posts the capture length in emulator steps and shows the pass badge, differences and overlay", async () => {
    routes["POST /api/hil/session/capture"] = () => json(201, { capture_id: "abc", valid: true, reason: "", clipped: 0 })
    routes["GET /api/hil/captures/abc/compare"] = () => json(200, {
      d_torque_pct: 1.25, d_irms_pct: -0.5, d_ripple_pts: 0.8, passed: true, clock_ratio: 1.00002, clock_measured: true, reason: "",
      ripple_window_hil: 103.4, ripple_window_sil: 78.25,
    })
    routes["GET /api/hil/captures/abc?n_px=1500"] = () => Promise.resolve(new Response(traces()))
    await mount()
    await emitLive(live())
    await setValue(document.getElementById("hil-capture-ms") as HTMLInputElement, "12")
    await act(async () => { button("Capture").click() })
    await vi.waitFor(() => expect(document.querySelector('[data-testid="scopes"]')).not.toBeNull())
    expect(calls.find((c) => c.url === "/api/hil/session/capture")!.body).toEqual({ n_steps: 2000 })
    expect(document.querySelector('[data-testid="verdict-pass"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="capture-invalid"]')).toBeNull()
    expect(text()).toContain("+1.25 %")
    expect(text()).toContain("-0.50 %")
    expect(text()).toContain("+0.80 pts")
    expect(text()).toContain("Ripple difference (median over strokes)")
    expect(text()).toContain("whole window: HIL 103.4 % · SIL 78.3 %")
    expect(document.querySelector('[data-testid="scopes"]')!.getAttribute("data-overlay")).toBe("sil.i.0")
  })

  it("shows the fail badge and the reason of a valid capture that missed the tolerance", async () => {
    routes["POST /api/hil/session/capture"] = () => json(201, { capture_id: "abc", valid: true, reason: "", clipped: 0 })
    routes["GET /api/hil/captures/abc/compare"] = () => json(200, {
      d_torque_pct: 9, d_irms_pct: 1, d_ripple_pts: 0, passed: false, clock_ratio: 1, clock_measured: true, reason: "parameters changed before the capture",
    })
    routes["GET /api/hil/captures/abc?n_px=1500"] = () => Promise.resolve(new Response(traces()))
    await mount()
    await emitLive(live())
    await act(async () => { button("Capture").click() })
    await vi.waitFor(() => expect(document.querySelector('[data-testid="verdict-fail"]')).not.toBeNull())
    expect(text()).toContain("parameters changed before the capture")
    expect(document.querySelector('[data-testid="verdict-pass"]')).toBeNull()
  })

  it("keeps a capture whose comparison failed, shows the error and retries", async () => {
    routes["POST /api/hil/session/capture"] = () => json(201, { capture_id: "abc", valid: true, reason: "", clipped: 0 })
    routes["GET /api/hil/captures/abc/compare"] = () => json(500, { detail: "the matched SIL run crashed" })
    await mount()
    await emitLive(live())
    await act(async () => { button("Capture").click() })
    expect(document.querySelector('[role="alert"]')?.textContent).toContain("Capture abc is stored")
    expect(text()).toContain("the matched SIL run crashed")
    expect(document.querySelector('[data-testid="verdict-pass"]')).toBeNull()
    routes["GET /api/hil/captures/abc/compare"] = () => json(200, { d_torque_pct: 1, d_irms_pct: 1, d_ripple_pts: 1, passed: true, clock_ratio: 1, clock_measured: true, reason: "" })
    routes["GET /api/hil/captures/abc?n_px=1500"] = () => Promise.resolve(new Response(traces()))
    await act(async () => { button("Retry").click() })
    await vi.waitFor(() => expect(document.querySelector('[data-testid="verdict-pass"]')).not.toBeNull())
    expect(calls.filter((c) => c.url === "/api/hil/session/capture")).toHaveLength(1)
  })

  it("rejects a capture length the server would refuse", async () => {
    await mount()
    await emitLive(live())
    await setValue(document.getElementById("hil-capture-ms") as HTMLInputElement, "5000")
    expect(button("Capture").disabled).toBe(true)
  })

  it("closes the event stream when it unmounts", async () => {
    await mount()
    const es = stream()
    expect(es.url).toBe("/api/hil/session/events")
    expect(es.closed).toBe(false)
    await act(async () => { roots.splice(0).forEach((r) => r.unmount()) })
    expect(es.closed).toBe(true)
  })
})
