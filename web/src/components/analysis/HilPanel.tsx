import { lazy, Suspense, useEffect, useRef, useState } from "react"
import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { useJobEvents } from "@/api/useJobEvents"
import type { ControllerInfo } from "@/api/control"
import { JobStepper } from "@/components/run/JobStepper"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { Scenario } from "@/lib/control"
import {
  captureSteps, hilCapture, hilCaptureTraces, hilClose, hilCommand, hilCompare, hilErrorText, hilFlash, hilFlashResult, hilOpen, hilParam,
  hilStart, hilStop, liveProblems, livePpm, MAX_CAPTURE_MS, MIN_CAPTURE_MS, paramStatusText, ppmOff, useHilEvents,
  type HilCaptureOut, type HilComparison, type HilFlashResult, type HilLive, type HilModes, type HilSession,
} from "@/lib/hil"

const ControlScopes = lazy(() => import("./ControlScopes"))
const SELECT = "min-h-11 w-full rounded-[6px] border border-border-strong bg-background px-2 font-mono text-[13px] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"

const num = (v: number | null | undefined, d: number, unit = "") => (v == null ? "n/a" : `${v.toFixed(d)}${unit ? ` ${unit}` : ""}`)
const signed = (v: number | null, d: number, unit: string) => (v == null ? "n/a" : `${v >= 0 ? "+" : "-"}${Math.abs(v).toFixed(d)} ${unit}`)
const ppmText = (ppm: number | null) => (ppm == null ? "not measured" : signed(Math.round(ppm), 0, "ppm"))

/** Label, value and an optional secondary line under the value. */
function Rows({ rows }: { rows: [string, string, string?][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm @2xl:grid-cols-4">
      {rows.map(([k, v, sub]) => (
        <div key={k}>
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="font-mono">{v}</dd>
          {sub && <dd className="text-xs text-muted-foreground">{sub}</dd>}
        </div>
      ))}
    </dl>
  )
}

function InvalidChip({ id, why }: { id: string; why: string }) {
  return <Badge variant="destructive" data-testid={id} title={why}>invalid</Badge>
}

/** `txBase` is the controller's dropped-frame counter before the run started. */
function LiveNumbers({ live, txBase }: { live: HilLive; txBase: number }) {
  const { emu, ctrl } = live
  const problems = liveProblems(live, txBase)
  const ppm = livePpm(live)
  const rows: [string, string][] = [
    ["Mean torque", num(emu?.mean_torque, 3, "N·m")],
    ["Torque ripple", num(emu?.ripple_pct, 1, "%")],
    ["RMS current", emu ? emu.i_rms.map((v) => num(v, 2)).join(" / ") + " A" : "n/a"],
    ["Speed", num(emu?.speed_rpm, 0, "rpm")],
    ["Emulator step", emu ? `${num(emu.step_mean_us, 1)} / ${num(emu.step_max_us, 1)} µs (mean / max), step ${emu.step}` : "n/a"],
    ["Controller ISR", ctrl ? `${num(ctrl.isr_mean_us, 1)} / ${num(ctrl.isr_max_us, 1)} µs (mean / max)` : "n/a"],
    ["Overruns", `step ${emu?.overruns ?? "n/a"} · ISR ${ctrl?.isr_overruns ?? "n/a"} · dropped ${emu?.dropped ?? "n/a"} · tx dropped ${ctrl ? ctrl.tx_dropped - txBase : "n/a"}`],
    ["Controller clock", ppm == null ? "not measured" : `${ppmText(ppm)} off nominal (measured)`],
  ]
  return (
    <div className="space-y-2" aria-label="Live numbers">
      <div className="flex flex-wrap items-center gap-2">
        {problems.length > 0 && <InvalidChip id="hil-invalid" why={problems.join("; ")} />}
        {problems.length > 0 && <span className="text-xs text-destructive">{problems.join("; ")}</span>}
      </div>
      <Rows rows={rows} />
    </div>
  )
}

/** Sends `ctrl_param` and keeps the reply's text. The same name and value are sent once; a refused or failed send, or a
 *  closed session, allows sending them again. */
function useParamSend(enabled: boolean) {
  const [status, setStatus] = useState<string | null>(null)
  const sent = useRef("")
  useEffect(() => {
    if (!enabled) {
      sent.current = ""
      setStatus(null)
    }
  }, [enabled])
  async function send(name: string, text: string) {
    const key = `${name}=${text}`
    if (!enabled || name.trim() === "" || text.trim() === "" || !Number.isFinite(Number(text)) || key === sent.current) return
    sent.current = key
    try {
      const reply = await hilParam(name.trim(), Number(text))
      setStatus(paramStatusText(reply.status))
      if (reply.status !== 0) sent.current = ""
    } catch (e) {
      sent.current = ""
      setStatus(hilErrorText(e))
    }
  }
  return { status, send }
}

const StatusText = ({ id, status }: { id: string; status: string | null }) =>
  status ? <p id={id} className={`text-xs ${status === "applied" ? "text-muted-foreground" : "text-destructive"}`} role="status">{status}</p> : null

/** One reference-controller parameter: sent when the field is left or Enter is pressed with a new number. */
function ParamRow({ p, enabled }: { p: ControllerInfo["params"][number]; enabled: boolean }) {
  const [text, setText] = useState("")
  const { status, send } = useParamSend(enabled)
  const id = `hil-p-${p.name}`
  const bad = text.trim() !== "" && !Number.isFinite(Number(text))
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{`${p.name} (${p.unit})`}</Label>
      <Input id={id} className="min-h-11 font-mono" placeholder={p.default} value={text} disabled={!enabled} aria-invalid={bad}
        onChange={(e) => setText(e.target.value)} onBlur={() => send(p.name, text)} onKeyDown={(e) => e.key === "Enter" && send(p.name, text)} />
      {bad && <p className="text-xs text-destructive">Enter a number.</p>}
      <StatusText id={`${id}-status`} status={status} />
    </div>
  )
}

/** A parameter of a custom controller, which has no entry in the reference list: name and value typed, sent with the button or Enter. */
function FreeParamRow({ n, enabled, onRemove }: { n: number; enabled: boolean; onRemove: () => void }) {
  const [name, setName] = useState("")
  const [text, setText] = useState("")
  const { status, send } = useParamSend(enabled)
  const bad = text.trim() !== "" && !Number.isFinite(Number(text))
  return (
    <div className="flex flex-wrap items-start gap-2">
      <Input aria-label={`Live parameter ${n} name`} className="min-h-11 w-44 font-mono" value={name} disabled={!enabled} maxLength={23}
        onChange={(e) => setName(e.target.value)} />
      <div className="space-y-1">
        <Input aria-label={`Live parameter ${n} value`} className="min-h-11 w-36 font-mono" value={text} disabled={!enabled} aria-invalid={bad}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(name, text)} />
        {bad && <p className="text-xs text-destructive">Enter a number.</p>}
        <StatusText id={`hil-fp-${n}-status`} status={status} />
      </div>
      <Button type="button" variant="outline" className="min-h-11" disabled={!enabled || name.trim() === "" || text.trim() === "" || bad} onClick={() => send(name, text)}>Send</Button>
      <Button type="button" variant="outline" className="min-h-11" onClick={onRemove}>Remove</Button>
    </div>
  )
}

/** The command of the running controller (N·m or rpm), sent when the field is left or Enter is pressed with a new number. */
function CommandRow({ scenario, enabled, onSession }: { scenario: Scenario; enabled: boolean; onSession: (s: HilSession) => void }) {
  const [mode, setMode] = useState<"torque" | "speed">(scenario.command_mode)
  const [text, setText] = useState(String(scenario.command_value))
  const [status, setStatus] = useState<string | null>(null)
  const sent = useRef("")
  const bad = text.trim() === "" || !Number.isFinite(Number(text))
  useEffect(() => {
    if (!enabled) sent.current = ""
  }, [enabled])
  async function send() {
    const key = `${mode}=${text}`
    if (!enabled || bad || key === sent.current) return
    sent.current = key
    try {
      onSession(await hilCommand(mode, Number(text)))
      setStatus(`commanded ${Number(text)} ${mode === "torque" ? "N·m" : "rpm"}`)
    } catch (e) {
      sent.current = ""
      setStatus(hilErrorText(e))
    }
  }
  return (
    <div className="flex flex-wrap items-start gap-3">
      <div className="space-y-1.5">
        <Label htmlFor="hil-cmd-mode">Command</Label>
        <select id="hil-cmd-mode" className={SELECT} value={mode} disabled={!enabled} onChange={(e) => setMode(e.target.value as "torque" | "speed")}>
          <option value="torque">Torque</option>
          <option value="speed">Speed</option>
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="hil-cmd-value">{mode === "torque" ? "Command (N·m)" : "Command (rpm)"}</Label>
        <Input id="hil-cmd-value" inputMode="decimal" className="min-h-11 w-36 font-mono" value={text} disabled={!enabled} aria-invalid={bad}
          onChange={(e) => setText(e.target.value)} onBlur={send} onKeyDown={(e) => e.key === "Enter" && send()} />
        {bad && <p className="text-xs text-destructive">Enter a number.</p>}
        <StatusText id="hil-cmd-status" status={status} />
      </div>
    </div>
  )
}

type CaptureView = {
  cap: HilCaptureOut
  cmp: HilComparison | null
  scopes: Awaited<ReturnType<typeof hilCaptureTraces>> | null
  /** Why the comparison or the traces could not be loaded; the capture itself is stored. */
  error: string | null
}

function CaptureResult({ view, busy, onRetry }: { view: CaptureView; busy: boolean; onRetry: () => void }) {
  const { cap, cmp, scopes, error } = view
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {!cap.valid && <InvalidChip id="capture-invalid" why={cap.reason} />}
        {cap.valid && cmp && (cmp.passed
          ? <Badge variant="ok" data-testid="verdict-pass">pass</Badge>
          : <Badge variant="destructive" data-testid="verdict-fail">fail</Badge>)}
        {cap.valid && cmp && !cmp.passed && cmp.reason && <span className="text-xs text-destructive">{cmp.reason}</span>}
        {!cap.valid && <span className="text-xs text-destructive">{cap.reason}</span>}
        {cap.clipped > 0 && <span className="text-xs text-muted-foreground">{(cap.clipped * 100).toFixed(1)} % of the samples are clipped at the capture current limit.</span>}
      </div>
      {error && (
        <div className="flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-destructive">{`Capture ${cap.capture_id} is stored, but its comparison could not be loaded: ${error}`}</p>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy} onClick={onRetry}>Retry</Button>
        </div>
      )}
      {cmp && cap.valid && (
        <Rows rows={[
          ["Torque difference", signed(cmp.d_torque_pct, 2, "%")],
          ["RMS current difference", signed(cmp.d_irms_pct, 2, "%")],
          ["Ripple difference (median over strokes)", signed(cmp.d_ripple_pts, 2, "pts"),
            `whole window: HIL ${num(cmp.ripple_window_hil, 1, "%")} · SIL ${num(cmp.ripple_window_sil, 1, "%")}`],
          ["Controller clock", cmp.clock_ratio == null ? "not measured" : `${ppmText(ppmOff(cmp.clock_ratio))} off nominal (${cmp.clock_measured ? "measured" : "assumed"})`],
        ]} />
      )}
      {scopes && (
        <Suspense fallback={<SrmSpinner label="Loading..." showLabel />}>
          <ControlScopes meta={scopes.meta} channels={scopes.channels} overlay={scopes.overlay} />
        </Suspense>
      )}
    </div>
  )
}

/** The HIL rig of the Control tab: build and flash both boards, open a live session, change the command and
 *  parameters, capture a run and compare it with the matched SIL run. */
export default function HilPanel({ caseId, controller, scenario, params, custom, invalid, activeFlashId }: {
  caseId: string
  controller: string
  scenario: Scenario
  /** The controller's parameters from the reference list; empty for a custom folder. */
  params: ControllerInfo["params"]
  /** True for a custom controller folder, whose live parameters are typed by name. */
  custom: boolean
  /** True while the controller or scenario fields are not valid. */
  invalid: boolean
  /** A Build & Flash job of the case that is queued or running, found after a reload. */
  activeFlashId?: string
}) {
  const [modes, setModes] = useState<HilModes>({ current_sense: "ad7606", position: "encoder", dac: "mcp4922x2" })
  const [flashId, setFlashId] = useState<string | null>(null)
  const [flashing, setFlashing] = useState(false)
  const [freeRows, setFreeRows] = useState<number[]>([])
  const nextRow = useRef(1)
  const [session, setSession] = useState<HilSession | null>(null)
  // A first stream attaches to a session that is already open (after a reload); opening one or reconnecting restarts it.
  const [epoch, setEpoch] = useState(0)
  const { live, ended, lost } = useHilEvents(epoch)
  // The controller's dropped-frame counter runs since boot; the last value seen while stopped is the run's baseline.
  const [txBase, setTxBase] = useState(0)
  const [captureMs, setCaptureMs] = useState("20")
  const [capture, setCapture] = useState<CaptureView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setup = { controller, scenario, modes }
  const steps = captureSteps(Number(captureMs))

  useEffect(() => { if (live) setSession(live.session) }, [live])
  useEffect(() => { if (live && !live.session.running && live.ctrl) setTxBase(live.ctrl.tx_dropped) }, [live])
  useEffect(() => { if (ended || lost) setSession(null) }, [ended, lost])
  // After a reload a queued or running flash job of the case is shown again.
  useEffect(() => { if (!flashId && activeFlashId) setFlashId(activeFlashId) }, [flashId, activeFlashId])

  async function act(fn: () => Promise<void>) {
    setError(null)
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      setError(hilErrorText(e))
    } finally {
      setBusy(false)
    }
  }

  /** The comparison and traces of a valid capture; when they fail the capture stays, with the error. */
  async function loadComparison(cap: HilCaptureOut) {
    try {
      const cmp = await hilCompare(cap.capture_id)
      setCapture({ cap, cmp, scopes: await hilCaptureTraces(cap.capture_id), error: null })
    } catch (e) {
      setCapture({ cap, cmp: null, scopes: null, error: hilErrorText(e) })
    }
  }

  return (
    <section className="space-y-4" aria-label="HIL rig">
      <div className="grid gap-3 @xl:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="hil-cs">Current sensing</Label>
          <select id="hil-cs" className={SELECT} value={modes.current_sense} onChange={(e) => setModes({ ...modes, current_sense: e.target.value as HilModes["current_sense"] })}>
            <option value="ad7606">AD7606</option>
            <option value="internal">Internal ADC</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="hil-pos">Position</Label>
          <select id="hil-pos" className={SELECT} value={modes.position} onChange={(e) => setModes({ ...modes, position: e.target.value as HilModes["position"] })}>
            <option value="encoder">Encoder</option>
            <option value="ad2s1210">AD2S1210 resolver</option>
            <option value="both">Both</option>
          </select>
        </div>
        {modes.current_sense === "internal" && (
          <div className="space-y-1.5">
            <Label htmlFor="hil-dac">DAC</Label>
            <select id="hil-dac" className={SELECT} value={modes.dac} onChange={(e) => setModes({ ...modes, dac: e.target.value as HilModes["dac"] })}>
              <option value="mcp4922x2">MCP4922 x 2</option>
              <option value="mcp4921x4">MCP4921 x 4</option>
            </select>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <Button type="button" className="min-h-11" disabled={invalid || !controller || busy || flashing || session !== null} onClick={() => act(async () => setFlashId((await hilFlash(caseId, setup)).job_id))}>
          Build &amp; Flash
        </Button>
        {flashId && <FlashView key={flashId} jobId={flashId} onActive={setFlashing} />}
      </div>

      <div className="space-y-3 border-t border-border pt-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" className="min-h-11" disabled={invalid || !controller || busy || flashing || session !== null}
            onClick={() => act(async () => { setSession(await hilOpen(caseId, setup)); setEpoch((e) => e + 1) })}>
            Open session
          </Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy || !session || session.running}
            onClick={() => act(async () => setSession(await hilStart()))}>Start</Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy || !session?.running} onClick={() => act(async () => setSession(await hilStop()))}>Stop</Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy} onClick={() => act(async () => { await hilClose(); setSession(null) })}>Close session</Button>
        </div>
        {error && <p role="alert" className="rounded-[10px] border border-destructive p-3 text-sm text-destructive">{error}</p>}
        <p className="text-sm text-muted-foreground" role="status">
          {session
            ? `Session open on case ${session.case_id}, ${session.controller}, ${session.modes.current_sense} / ${session.modes.position}; emulator firmware ${session.emulator_hash.toString(16)}, controller firmware ${session.controller_hash.toString(16)}; ${session.running ? "running" : "stopped"}.`
            : "No session open."}
        </p>
        {lost && (
          <div className="flex flex-wrap items-center gap-3" role="alert">
            <p className="text-sm text-destructive">The live connection closed. The session may still be open on the server.</p>
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setEpoch((e) => e + 1)}>Reconnect</Button>
          </div>
        )}
        {live && <LiveNumbers live={live} txBase={txBase} />}
      </div>

      <div className="space-y-3 border-t border-border pt-4">
        <CommandRow scenario={scenario} enabled={session !== null} onSession={setSession} />
        {params.length > 0 && (
          <fieldset className="grid gap-3 @2xl:grid-cols-3">
            <legend className="mb-1 text-sm font-medium">Parameters (sent when you leave the field or press Enter)</legend>
            {params.map((p) => <ParamRow key={p.name} p={p} enabled={session !== null} />)}
          </fieldset>
        )}
        {custom && (
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">Live parameters (name and value)</legend>
            {freeRows.map((n, i) => <FreeParamRow key={n} n={i + 1} enabled={session !== null} onRemove={() => setFreeRows((r) => r.filter((x) => x !== n))} />)}
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setFreeRows((r) => [...r, nextRow.current++])}>Add live parameter</Button>
          </fieldset>
        )}
      </div>

      <div className="space-y-3 border-t border-border pt-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="hil-capture-ms">Capture length (ms)</Label>
            <Input id="hil-capture-ms" inputMode="decimal" className="min-h-11 w-32 font-mono" value={captureMs} aria-invalid={steps === null}
              aria-describedby={steps === null ? "hil-capture-err" : undefined} onChange={(e) => setCaptureMs(e.target.value)} />
          </div>
          <Button type="button" className="min-h-11" disabled={busy || !session?.running || steps === null}
            onClick={() => act(async () => {
              setCapture(null)
              const cap = await hilCapture(steps!)
              if (cap.valid) await loadComparison(cap)
              else setCapture({ cap, cmp: null, scopes: null, error: null })
            })}>
            Capture
          </Button>
        </div>
        {steps === null && <p id="hil-capture-err" className="text-xs text-destructive">{`Enter a length from ${MIN_CAPTURE_MS} to ${MAX_CAPTURE_MS} ms.`}</p>}
        {busy && session?.running && <SrmSpinner label="Capturing and comparing..." showLabel />}
        {capture && <CaptureResult view={capture} busy={busy} onRetry={() => act(() => loadComparison(capture.cap))} />}
      </div>
    </section>
  )
}

/** The Build & Flash job: its steps, and the end of the PlatformIO log (open when the job failed). `onActive` tells the
 *  panel whether the job is still queued or running. */
function FlashView({ jobId, onActive }: { jobId: string; onActive: (active: boolean) => void }) {
  const { job } = useJobEvents(jobId)
  const [result, setResult] = useState<HilFlashResult | null>(null)
  useEffect(() => onActive(!job || job.active), [job, onActive])
  useEffect(() => () => onActive(false), [onActive])
  const done = job?.status === "done"
  useEffect(() => {
    if (done) hilFlashResult(jobId).then(setResult).catch(() => {})
  }, [done, jobId])
  if (!job) return <SrmSpinner label="Starting..." showLabel />
  const log = job.error ?? result?.log
  return (
    <div className="space-y-2">
      <JobStepper job={job} />
      {!job.active && !done && (
        <p role="alert" className="text-sm text-destructive">{job.status === "failed" ? "Build & Flash failed." : `Build & Flash ${job.status}.`}</p>
      )}
      {log && (
        <details open={!!job.error} className="rounded-[10px] border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">Build log</summary>
          <pre className={`mt-2 max-h-80 overflow-auto font-mono text-xs whitespace-pre-wrap ${job.error ? "text-destructive" : ""}`}>{log}</pre>
        </details>
      )}
    </div>
  )
}
