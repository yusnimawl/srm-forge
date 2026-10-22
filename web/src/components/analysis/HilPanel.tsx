import { lazy, Suspense, useEffect, useState } from "react"
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
  captureSteps, hilCapture, hilCaptureTraces, hilClose, hilCompare, hilErrorText, hilFlash, hilOpen, hilParam, hilStart, hilStop,
  liveProblems, livePpm, MAX_CAPTURE_MS, MIN_CAPTURE_MS, paramStatusText, ppmOff, useHilEvents,
  type HilCaptureOut, type HilComparison, type HilLive, type HilModes, type HilSession,
} from "@/lib/hil"

const ControlScopes = lazy(() => import("./ControlScopes"))
const SELECT = "min-h-11 w-full rounded-[6px] border border-border-strong bg-background px-2 font-mono text-[13px] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"

const num = (v: number | null | undefined, d: number, unit = "") => (v == null ? "n/a" : `${v.toFixed(d)}${unit ? ` ${unit}` : ""}`)
const signed = (v: number | null, d: number, unit: string) => (v == null ? "n/a" : `${v >= 0 ? "+" : "-"}${Math.abs(v).toFixed(d)} ${unit}`)
const ppmText = (ppm: number | null) => (ppm == null ? "not measured" : signed(Math.round(ppm), 0, "ppm"))

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm @2xl:grid-cols-4">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="font-mono">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function InvalidChip({ id, why }: { id: string; why: string }) {
  return <Badge variant="destructive" data-testid={id} title={why}>invalid</Badge>
}

function LiveNumbers({ live }: { live: HilLive }) {
  const { emu, ctrl } = live
  const problems = liveProblems(live)
  const ppm = livePpm(live)
  const rows: [string, string][] = [
    ["Mean torque", num(emu?.mean_torque, 3, "N·m")],
    ["Torque ripple", num(emu?.ripple_pct, 1, "%")],
    ["RMS current", emu ? emu.i_rms.map((v) => num(v, 2)).join(" / ") + " A" : "n/a"],
    ["Speed", num(emu?.speed_rpm, 0, "rpm")],
    ["Emulator step", emu ? `${num(emu.step_mean_us, 1)} / ${num(emu.step_max_us, 1)} µs (mean / max), step ${emu.step}` : "n/a"],
    ["Controller ISR", ctrl ? `${num(ctrl.isr_mean_us, 1)} / ${num(ctrl.isr_max_us, 1)} µs (mean / max)` : "n/a"],
    ["Overruns", `step ${emu?.overruns ?? "n/a"} · ISR ${ctrl?.isr_overruns ?? "n/a"} · dropped ${emu?.dropped ?? "n/a"} · tx dropped ${ctrl?.tx_dropped ?? "n/a"}`],
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

/** One controller parameter: sent when the field is left or Enter is pressed with a new number; the reply is shown beside it. */
function ParamRow({ p, enabled }: { p: ControllerInfo["params"][number]; enabled: boolean }) {
  const [text, setText] = useState("")
  const [sent, setSent] = useState("")
  const [status, setStatus] = useState<string | null>(null)
  const id = `hil-p-${p.name}`
  const bad = text.trim() !== "" && !Number.isFinite(Number(text))
  async function send() {
    if (!enabled || text.trim() === "" || bad || text === sent) return
    setSent(text)
    try {
      setStatus(paramStatusText((await hilParam(p.name, Number(text))).status))
    } catch (e) {
      setStatus(hilErrorText(e))
    }
  }
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{`${p.name} (${p.unit})`}</Label>
      <Input id={id} className="min-h-11 font-mono" placeholder={p.default} value={text} disabled={!enabled} aria-invalid={bad}
        onChange={(e) => setText(e.target.value)} onBlur={send} onKeyDown={(e) => e.key === "Enter" && send()} />
      {bad && <p className="text-xs text-destructive">Enter a number.</p>}
      {status && <p id={`${id}-status`} className={`text-xs ${status === "applied" ? "text-muted-foreground" : "text-destructive"}`} role="status">{status}</p>}
    </div>
  )
}

type CaptureView = { cap: HilCaptureOut; cmp: HilComparison | null; scopes: Awaited<ReturnType<typeof hilCaptureTraces>> | null }

function CaptureResult({ view }: { view: CaptureView }) {
  const { cap, cmp, scopes } = view
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
      {cmp && cap.valid && (
        <Rows rows={[
          ["Torque difference", signed(cmp.d_torque_pct, 2, "%")],
          ["RMS current difference", signed(cmp.d_irms_pct, 2, "%")],
          ["Ripple difference", signed(cmp.d_ripple_pts, 2, "pts")],
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

/** The HIL rig of the Control tab: build and flash both boards, open a live session, change parameters, capture a
 *  run and compare it with the matched SIL run. */
export default function HilPanel({ caseId, controller, scenario, params, invalid }: {
  caseId: string
  controller: string
  scenario: Scenario
  params: ControllerInfo["params"]
  /** True while the controller or scenario fields are not valid. */
  invalid: boolean
}) {
  const [modes, setModes] = useState<HilModes>({ current_sense: "ad7606", position: "encoder", dac: "mcp4922x2" })
  const [flashId, setFlashId] = useState<string | null>(null)
  const [session, setSession] = useState<HilSession | null>(null)
  // A first stream attaches to a session that is already open (after a reload); opening one reconnects.
  const [epoch, setEpoch] = useState(0)
  const { live, ended } = useHilEvents(epoch)
  const [captureMs, setCaptureMs] = useState("20")
  const [capture, setCapture] = useState<CaptureView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setup = { controller, scenario, modes }
  const steps = captureSteps(Number(captureMs))

  useEffect(() => { if (live) setSession(live.session) }, [live])
  useEffect(() => { if (ended) setSession(null) }, [ended])

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
        <Button type="button" className="min-h-11" disabled={invalid || !controller || busy || session !== null} onClick={() => act(async () => setFlashId((await hilFlash(caseId, setup)).job_id))}>
          Build &amp; Flash
        </Button>
        {flashId && <FlashView key={flashId} jobId={flashId} />}
      </div>

      <div className="space-y-3 border-t border-border pt-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" className="min-h-11" disabled={invalid || !controller || busy || session !== null}
            onClick={() => act(async () => { setSession(await hilOpen(caseId, setup)); setEpoch((e) => e + 1) })}>
            Open session
          </Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy || !session || session.running} onClick={() => act(async () => setSession(await hilStart()))}>Start</Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy || !session?.running} onClick={() => act(async () => setSession(await hilStop()))}>Stop</Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy || !session} onClick={() => act(async () => { await hilClose(); setSession(null) })}>Close session</Button>
        </div>
        {error && <p role="alert" className="rounded-[10px] border border-destructive p-3 text-sm text-destructive">{error}</p>}
        <p className="text-sm text-muted-foreground" role="status">
          {session
            ? `Session open on case ${session.case_id}, ${session.controller}, ${session.modes.current_sense} / ${session.modes.position}; emulator firmware ${session.emulator_hash.toString(16)}, controller firmware ${session.controller_hash.toString(16)}; ${session.running ? "running" : "stopped"}.`
            : "No session open."}
        </p>
        {live && <LiveNumbers live={live} />}
      </div>

      {params.length > 0 && (
        <fieldset className="grid gap-3 border-t border-border pt-4 @2xl:grid-cols-3">
          <legend className="mb-1 text-sm font-medium">Parameters (sent when you leave the field or press Enter)</legend>
          {params.map((p) => <ParamRow key={p.name} p={p} enabled={session !== null} />)}
        </fieldset>
      )}

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
              if (!cap.valid) return setCapture({ cap, cmp: null, scopes: null })
              const cmp = await hilCompare(cap.capture_id)
              setCapture({ cap, cmp, scopes: await hilCaptureTraces(cap.capture_id) })
            })}>
            Capture
          </Button>
        </div>
        {steps === null && <p id="hil-capture-err" className="text-xs text-destructive">{`Enter a length from ${MIN_CAPTURE_MS} to ${MAX_CAPTURE_MS} ms.`}</p>}
        {busy && session?.running && <SrmSpinner label="Capturing and comparing..." showLabel />}
        {capture && <CaptureResult view={capture} />}
      </div>
    </section>
  )
}

/** The Build & Flash job: its steps, and the end of the PlatformIO log when it failed. */
function FlashView({ jobId }: { jobId: string }) {
  const { job } = useJobEvents(jobId)
  if (!job) return <SrmSpinner label="Starting..." showLabel />
  return (
    <div className="space-y-2">
      <JobStepper job={job} />
      {!job.active && job.status !== "done" && (
        <p role="alert" className="text-sm text-destructive">{job.status === "failed" ? "Build & Flash failed." : `Build & Flash ${job.status}.`}</p>
      )}
      {job.error && <pre className="max-h-80 overflow-auto rounded-[10px] border border-destructive p-3 font-mono text-xs whitespace-pre-wrap">{job.error}</pre>}
    </div>
  )
}
