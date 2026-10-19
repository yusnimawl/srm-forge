import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { lazy, Suspense, useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "@/api/client"
import type { Case } from "@/api/types"
import { useControllers, useControlScopes, useRunControl, useTargetCheck } from "@/api/control"
import { useJobActions } from "@/api/useJobActions"
import { useJobEvents } from "@/api/useJobEvents"
import { JobStepper } from "@/components/run/JobStepper"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { defaultIsrHz, defaultScenario, scenarioErrors, type ControlSummary, type Scenario } from "@/lib/control"
import { errorMessage } from "@/lib/errorMessage"

const ControlScopes = lazy(() => import("./ControlScopes"))
const CUSTOM = "__custom__"
const SELECT = "min-h-11 w-full rounded-[6px] border border-border-strong bg-background px-2 font-mono text-[13px] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"

/** A number input that keeps the text being typed; `scale` converts the stored value to the displayed unit. */
function NumField({ id, label, value, onChange, scale = 1, error }: {
  id: string
  label: string
  value: number | null
  onChange: (v: number) => void
  scale?: number
  error?: string
}) {
  const [text, setText] = useState(() => (value == null ? "" : String(+(value * scale).toPrecision(8))))
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} inputMode="decimal" className="min-h-11 font-mono" value={text} aria-invalid={!!error}
        aria-describedby={error ? `${id}-err` : undefined}
        onChange={(e) => {
          setText(e.target.value)
          onChange(e.target.value.trim() === "" ? NaN : Number(e.target.value) / scale)
        }} />
      {error && <p id={`${id}-err`} className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

const pct = (v: number | null) => (v == null ? "n/a" : `${v.toFixed(1)} %`)
const fix = (v: number | null, d: number, unit: string) => (v == null ? "n/a" : `${v.toFixed(d)} ${unit}`)

function Summary({ s }: { s: ControlSummary }) {
  const beyond = (s.beyond_map_fraction ?? 0) * 100
  const rows: [string, string][] = [
    ["Mean torque", fix(s.mean_torque, 3, "N·m")],
    ["Torque ripple", pct(s.ripple_pct)],
    ["RMS current", s.i_rms.map((v) => v.toFixed(2)).join(" / ") + " A"],
    ["Copper loss", fix(s.copper_loss, 1, "W")],
    ["Input power", fix(s.power_in, 1, "W")],
    ["Mechanical power", fix(s.power_mech, 1, "W")],
    ["Energy round trip error", s.roundtrip_error == null ? "n/a" : `${(s.roundtrip_error * 100).toFixed(2)} %`],
    ["Beyond the map", `${beyond.toFixed(2)} %`],
  ]
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm @2xl:grid-cols-4">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-mono">{v}</dd>
          </div>
        ))}
      </dl>
      {beyond > 0 && (
        <p role="status" className="inline-block rounded-[6px] border border-destructive px-2 py-1 text-xs text-destructive">
          The run drove current beyond the map; the tables extrapolate there, so read the results with care.
        </p>
      )}
      <p className="text-xs text-muted-foreground">Phases uncoupled: mutual flux between phases is not modelled.</p>
    </div>
  )
}

/** A running or finished control job: steps, failure log, or the scopes with their summary. */
function RunView({ caseId, jobId, onBusy }: { caseId: string; jobId: string; onBusy: (busy: boolean) => void }) {
  const { job } = useJobEvents(jobId)
  const qc = useQueryClient()
  const actions = useJobActions()
  const [zoomed, setZoomed] = useState(false)
  const base = Math.min(10000, Math.max(100, Math.round(window.innerWidth)))
  const done = job?.status === "done"
  const scopes = useControlScopes(done ? jobId : null, zoomed ? Math.min(10000, base * 4) : base)
  // Busy until the job is known to have ended; a final status also refreshes the case so its job list is current.
  useEffect(() => onBusy(!job || job.active), [job, onBusy])
  const final = !!job && !job.active
  useEffect(() => {
    if (final) qc.invalidateQueries({ queryKey: ["case", caseId] })
  }, [final, qc, caseId])
  useEffect(() => () => onBusy(false), [onBusy])

  if (!job) return <SrmSpinner label="Loading the run..." showLabel />
  if (job.active)
    return (
      <div className="space-y-2 rounded-[10px] border border-border bg-card p-3">
        <JobStepper job={job} />
        <Button type="button" variant="outline" className="min-h-11" disabled={actions.busy} onClick={() => actions.cancel(jobId)}>Cancel</Button>
      </div>
    )
  if (!done)
    return (
      <div className="space-y-2">
        <JobStepper job={job} />
        <p role="alert" className="text-sm text-destructive">{job.status === "failed" ? "The run failed." : `The run ${job.status}.`}</p>
        {job.error && <pre className="max-h-80 overflow-auto rounded-[10px] border border-destructive p-3 font-mono text-xs whitespace-pre-wrap">{job.error}</pre>}
      </div>
    )
  if (!scopes.data) {
    return scopes.isPending ? <SrmSpinner label="Loading the traces..." showLabel /> : <p role="alert" className="text-sm text-destructive">{errorMessage(scopes.error)}</p>
  }
  return (
    <div className="space-y-3">
      <Summary s={scopes.data.meta.summary} />
      <Suspense fallback={<SrmSpinner label="Loading..." showLabel />}>
        <ControlScopes meta={scopes.data.meta} channels={scopes.data.channels} onZoom={setZoomed} />
      </Suspense>
    </div>
  )
}

/** Runs a controller against an evaluated case's motor model and shows the scopes. */
export default function ControlTab({ caseId, busVoltage, peakTorque, baseSpeedRpm }: { caseId: string; busVoltage?: number; peakTorque?: number | null; baseSpeedRpm?: number }) {
  const controllers = useControllers()
  const run = useRunControl(caseId)
  const check = useTargetCheck(caseId)
  const caseQ = useQuery({ queryKey: ["case", caseId], queryFn: () => api<Case>(`/api/cases/${caseId}`) })
  const [choice, setChoice] = useState("hysteresis")
  const [folder, setFolder] = useState("")
  const [params, setParams] = useState<Record<string, string>>({})
  const [sc, setSc] = useState<Scenario>(() => ({ ...defaultScenario(busVoltage, peakTorque, baseSpeedRpm), isr_hz: defaultIsrHz("hysteresis") }))
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [custom, setCustom] = useState<{ name: string; value: string }[]>([])
  const [headerError, setHeaderError] = useState<string | null>(null)

  const info = controllers.data?.find((c) => c.name === choice)
  const controller = choice === CUSTOM ? folder.trim() : choice
  const patch = (p: Partial<Scenario>) => setSc((s) => ({ ...s, ...p }))
  const sub = <K extends "converter" | "sensors" | "adc">(k: K, p: Partial<Scenario[K]>) => setSc((s) => ({ ...s, [k]: { ...s[k], ...p } }))
  const errors = scenarioErrors(sc)
  const paramErrors = Object.fromEntries(Object.entries(params).filter(([, v]) => v.trim() !== "" && !Number.isFinite(Number(v))).map(([k]) => [k, "Enter a number."]))
  const entered = Object.fromEntries(Object.entries(params).filter(([, v]) => v.trim() !== "" && Number.isFinite(Number(v))).map(([k, v]) => [k, Number(v)]))
  const customErrors = choice === CUSTOM ? custom.map((r, i) => ({
    name: r.name.trim() === "" ? "Enter a name." : custom.some((o, j) => j !== i && o.name.trim() === r.name.trim()) ? "Names must be unique." : undefined,
    value: r.value.trim() === "" || !Number.isFinite(Number(r.value)) ? "Enter a number." : undefined,
  })) : []
  const customInvalid = customErrors.some((e) => e.name || e.value)
  const sent = choice === CUSTOM ? Object.fromEntries(custom.map((r) => [r.name.trim(), Number(r.value)])) : entered
  const folderError = choice === CUSTOM && !folder.trim() ? "Enter the absolute path of the controller folder." : undefined
  const invalid = Object.keys(errors).length > 0 || Object.keys(paramErrors).length > 0 || !!folderError || customInvalid
  const last = (caseQ.data?.jobs ?? []).filter((j) => j.kind === "control" && j.status === "done").sort((a, b) => b.created.localeCompare(a.created))[0]
  const running = busy || run.isPending
  // After a reload a running job is picked up from the case's job list.
  const active = (caseQ.data?.jobs ?? []).find((j) => j.kind === "control" && j.active)
  useEffect(() => {
    if (!jobId && active) setJobId(active.id)
  }, [jobId, active])
  async function downloadHeader() {
    setHeaderError(null)
    try {
      const res = await fetch(`/api/cases/${caseId}/control/header`, { credentials: "same-origin" })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new ApiError(res.status, body?.detail ?? res.statusText, body)
      }
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement("a")
      a.href = url
      a.download = "srm_motor_tables.h"
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setHeaderError(errorMessage(e))
    }
  }
  const bus = sc.bus_voltage ?? busVoltage

  return (
    <div className="@container space-y-4 pt-2">
      <section className="space-y-3" aria-label="Controller">
        <div className="grid gap-3 @2xl:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="ctl-controller">Controller</Label>
            <select id="ctl-controller" className={SELECT} value={choice} onChange={(e) => { setChoice(e.target.value); setParams({}); patch({ isr_hz: defaultIsrHz(e.target.value) }) }}>
              {(controllers.data ?? []).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
              <option value={CUSTOM}>Custom folder…</option>
            </select>
          </div>
          {choice === CUSTOM && (
            <div className="space-y-1.5">
              <Label htmlFor="ctl-folder">Controller folder (absolute path)</Label>
              <Input id="ctl-folder" className="min-h-11 font-mono" value={folder} aria-invalid={!!folderError} aria-describedby={folderError ? "ctl-folder-err" : undefined} onChange={(e) => setFolder(e.target.value)} />
              {folderError && <p id="ctl-folder-err" className="text-xs text-destructive">{folderError}</p>}
            </div>
          )}
        </div>
        {choice === CUSTOM && (
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">Parameters (name and value)</legend>
            {custom.map((r, i) => (
              <div key={i} className="flex flex-wrap items-start gap-2">
                <div className="space-y-1">
                  <Input aria-label={`Parameter ${i + 1} name`} className="min-h-11 font-mono" value={r.name} aria-invalid={!!customErrors[i]?.name}
                    aria-describedby={customErrors[i]?.name ? `ctl-cn-${i}-err` : undefined}
                    onChange={(e) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                  {customErrors[i]?.name && <p id={`ctl-cn-${i}-err`} className="text-xs text-destructive">{customErrors[i]?.name}</p>}
                </div>
                <div className="space-y-1">
                  <Input aria-label={`Parameter ${i + 1} value`} className="min-h-11 font-mono" value={r.value} aria-invalid={!!customErrors[i]?.value}
                    aria-describedby={customErrors[i]?.value ? `ctl-cv-${i}-err` : undefined}
                    onChange={(e) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                  {customErrors[i]?.value && <p id={`ctl-cv-${i}-err`} className="text-xs text-destructive">{customErrors[i]?.value}</p>}
                </div>
                <Button type="button" variant="outline" className="min-h-11" onClick={() => setCustom((c) => c.filter((_, j) => j !== i))}>Remove</Button>
              </div>
            ))}
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setCustom((c) => [...c, { name: "", value: "" }])}>Add parameter</Button>
          </fieldset>
        )}
        {info && info.params.length > 0 && (
          <fieldset className="grid gap-3 @2xl:grid-cols-3">
            <legend className="mb-1 text-sm font-medium">Parameters (empty uses the default)</legend>
            {info.params.map((p) => (
              <div key={p.name} className="space-y-1.5">
                <Label htmlFor={`ctl-p-${p.name}`}>{`${p.name} (${p.unit})`}</Label>
                <Input id={`ctl-p-${p.name}`} className="min-h-11 font-mono" placeholder={p.default} value={params[p.name] ?? ""}
                  aria-invalid={!!paramErrors[p.name]} aria-describedby={paramErrors[p.name] ? `ctl-p-${p.name}-err` : undefined} onChange={(e) => setParams((s) => ({ ...s, [p.name]: e.target.value }))} />
                {paramErrors[p.name] && <p id={`ctl-p-${p.name}-err`} className="text-xs text-destructive">{paramErrors[p.name]}</p>}
              </div>
            ))}
          </fieldset>
        )}
      </section>

      <section className="space-y-3 border-t border-border pt-4" aria-label="Scenario">
        <div className="grid gap-3 @xl:grid-cols-3 @3xl:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="ctl-mode">Mode</Label>
            <select id="ctl-mode" className={SELECT} value={sc.mode} onChange={(e) => patch({ mode: e.target.value as Scenario["mode"] })}>
              <option value="fixed">Fixed speed</option>
              <option value="dynamic">Dynamic (free speed)</option>
            </select>
          </div>
          <NumField id="ctl-speed" label={sc.mode === "fixed" ? "Speed (rpm)" : "Initial speed (rpm)"} value={sc.speed_rpm} onChange={(v) => patch({ speed_rpm: v })} error={errors.speed_rpm} />
          <NumField id="ctl-duration" label="Duration (ms)" value={sc.duration} scale={1e3} onChange={(v) => patch({ duration: v })} error={errors.duration} />
          <div className="space-y-1.5">
            <Label htmlFor="ctl-cmode">Command</Label>
            <select id="ctl-cmode" className={SELECT} value={sc.command_mode} onChange={(e) => patch({ command_mode: e.target.value as Scenario["command_mode"] })}>
              <option value="torque">Torque</option>
              <option value="speed">Speed</option>
            </select>
          </div>
          <NumField id="ctl-cvalue" label={sc.command_mode === "torque" ? "Command (N·m)" : "Command (rpm)"} value={sc.command_value} onChange={(v) => patch({ command_value: v })} error={errors.command_value} />
          <NumField id="ctl-inertia" label="Inertia J (kg·m²)" value={sc.inertia} onChange={(v) => patch({ inertia: v })} error={errors.inertia} />
          <NumField id="ctl-friction" label="Friction B (N·m·s/rad)" value={sc.friction} onChange={(v) => patch({ friction: v })} error={errors.friction} />
          <NumField id="ctl-load" label="Load (N·m)" value={sc.load} onChange={(v) => patch({ load: v })} error={errors.load} />
          <NumField id="ctl-lstep" label="Load step (N·m)" value={sc.load_step} onChange={(v) => patch({ load_step: v })} error={errors.load_step} />
          <NumField id="ctl-lstept" label="Load step at (ms)" value={sc.load_step_time} scale={1e3} onChange={(v) => patch({ load_step_time: v })} error={errors.load_step_time} />
        </div>
        <details className="rounded-[10px] border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">Hardware</summary>
          <div className="mt-3 grid gap-3 @xl:grid-cols-3 @3xl:grid-cols-4">
            <NumField id="ctl-bus" label="Bus voltage (V)" value={sc.bus_voltage ?? busVoltage ?? null} onChange={(v) => patch({ bus_voltage: v })} error={errors.bus_voltage} />
            <NumField id="ctl-dt" label="Time step (µs)" value={sc.dt} scale={1e6} onChange={(v) => patch({ dt: v })} error={errors.dt} />
            <NumField id="ctl-pwm" label="PWM frequency (Hz)" value={sc.pwm_hz} onChange={(v) => patch({ pwm_hz: v })} error={errors.pwm_hz} />
            <NumField key={`isr-${choice}`} id="ctl-isr" label="ISR rate (kHz, empty = PWM rate)" value={sc.isr_hz ?? null} scale={1e-3} onChange={(v) => patch({ isr_hz: Number.isNaN(v) ? null : v })} error={errors.isr_hz} />
            <NumField id="ctl-dead" label="Dead time (µs)" value={sc.converter.dead_time} scale={1e6} onChange={(v) => sub("converter", { dead_time: v })} error={errors["converter.dead_time"]} />
            <NumField id="ctl-vsw" label="Switch drop (V)" value={sc.converter.v_switch} onChange={(v) => sub("converter", { v_switch: v })} error={errors["converter.v_switch"]} />
            <NumField id="ctl-cpr" label="Encoder counts / rev" value={sc.sensors.encoder_cpr} onChange={(v) => sub("sensors", { encoder_cpr: v })} error={errors["sensors.encoder_cpr"]} />
            <NumField id="ctl-bits" label="ADC bits" value={sc.adc.bits} onChange={(v) => sub("adc", { bits: v })} error={errors["adc.bits"]} />
            <NumField id="ctl-aoff" label="ADC offset (counts)" value={sc.adc.offset_counts} onChange={(v) => sub("adc", { offset_counts: v })} error={errors["adc.offset_counts"]} />
            <NumField id="ctl-anoise" label="ADC noise (counts)" value={sc.adc.noise} onChange={(v) => sub("adc", { noise: v })} error={errors["adc.noise"]} />
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="size-5 accent-primary" checked={sc.sensors.resolver} onChange={(e) => sub("sensors", { resolver: e.target.checked })} />
              Resolver
            </label>
          </div>
        </details>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" className="min-h-11" disabled={invalid || running || !controller}
            onClick={() => run.mutate({ controller, scenario: { ...sc, bus_voltage: bus ?? null, params: sent } }, { onSuccess: (r) => setJobId(r.job_id) })}>
            {run.isPending ? "Starting..." : "Run"}
          </Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={!controller || check.isPending} onClick={() => check.mutate(controller)}>
            {check.isPending ? "Checking..." : "Check for target"}
          </Button>
          <Button type="button" variant="outline" className="min-h-11" onClick={downloadHeader}>Download srm_motor_tables.h</Button>
          {last && last.id !== jobId && (
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setJobId(last.id)}>Load the last run</Button>
          )}
        </div>
        {headerError && <p role="alert" className="rounded-[10px] border border-destructive p-3 text-sm text-destructive">{headerError}</p>}
        {run.error && <p role="alert" className="rounded-[10px] border border-destructive p-3 text-sm text-destructive">{errorMessage(run.error)}</p>}
        {check.error && <p role="alert" className="rounded-[10px] border border-destructive p-3 text-sm text-destructive">{errorMessage(check.error)}</p>}
        {check.data && (
          <div className="space-y-1" role="status">
            <p className={`text-sm font-medium ${check.data.ok ? "" : "text-destructive"}`}>
              {check.data.ok ? `Target check passed (${check.data.compiler})` : `Target check failed (${check.data.compiler})`}
            </p>
            {check.data.log && <pre className="max-h-60 overflow-auto rounded-[10px] border border-border p-3 font-mono text-xs whitespace-pre-wrap">{check.data.log}</pre>}
          </div>
        )}
      </section>

      {jobId && (
        <section className="border-t border-border pt-4" aria-label="Run">
          <RunView key={jobId} caseId={caseId} jobId={jobId} onBusy={setBusy} />
        </section>
      )}
    </div>
  )
}
