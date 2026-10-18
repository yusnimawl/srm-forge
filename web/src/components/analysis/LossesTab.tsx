import { useCallback, useEffect, useMemo, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import type { Data, Layout } from "plotly.js-dist-min"
import { api } from "@/api/client"
import type { Case } from "@/api/types"
import { lossesMessage, useLossB, useLosses, useLossesEstimate, useRunLosses } from "@/api/losses"
import { useJobEvents } from "@/api/useJobEvents"
import type { Geometry } from "@/components/candidate/MotorDiagram"
import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { LinePlot, Plot, plotTheme, useColors } from "@/components/PlotlyPlot"
import { JobStepper } from "@/components/run/JobStepper"
import { Chip } from "@/components/StatusChips"
import { Button } from "@/components/ui/button"
import { SELECT_CLASS } from "@/components/case/fields"
import { LINE_COLORS } from "@/lib/analysis"
import { lossChips } from "@/lib/chips"
import { fmt } from "@/lib/format"
import { INFERNO_SCALE } from "@/lib/inferno"
import { bestPoint, contourData, pointLabel, ratedPoint, splitBars, svgToMetres, type LossesResult } from "@/lib/losses"
import { fmtAbout } from "@/lib/steps"

const HEADING = "text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground"

/** Click an iron element of the outline; reports the position in metres in the stator frame at rotor angle 0. */
function ElementPicker({ machine, onPick }: { machine: object; onPick: (at: { x: number; y: number }) => void }) {
  const geo = useQuery({
    queryKey: ["geometry", machine],
    queryFn: () => api<Geometry>("/api/geometry", { method: "POST", body: JSON.stringify(machine) }),
    retry: false,
  })
  const [mark, setMark] = useState<{ x: number; y: number } | null>(null)
  if (!geo.data) return <div className="h-64" aria-busy={geo.isPending} />
  const g = geo.data
  return (
    <svg
      viewBox={g.view_box.join(" ")}
      role="img"
      aria-label="Pick an iron element"
      className="mx-auto h-auto w-full max-w-[300px] cursor-crosshair"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        const at = svgToMetres(r, g.view_box, e.clientX, e.clientY)
        setMark({ x: at.x * 1000, y: -at.y * 1000 })
        onPick(at)
      }}
    >
      <path d={g.stator} fillRule="evenodd" fill="var(--iron)" stroke="var(--iron-edge)" strokeWidth={0.2} />
      <path d={g.rotor} fillRule="evenodd" fill="var(--iron)" stroke="var(--iron-edge)" strokeWidth={0.2} />
      {mark && <circle cx={mark.x} cy={mark.y} r={1.2} fill={LINE_COLORS[1]} />}
    </svg>
  )
}

function Results({ caseId, r, machine }: { caseId: string; r: LossesResult; machine: object | undefined }) {
  const colors = useColors()
  const theme = plotTheme(colors)
  const best = bestPoint(r)
  const [picked, setPicked] = useState<number | null>(null)
  const sel = picked ?? Math.max(best, 0)
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const b = useLossB(caseId, sel, at)
  const c = contourData(r)
  const bars = splitBars(r)
  const rated = ratedPoint(r)
  const nt = r.torque_fractions.length
  const reached = r.points.map((p, k) => [p, k] as const).filter(([p]) => p.reached)
  const labels = r.points.map(pointLabel)

  const contour: Data[] = [
    {
      type: "contour", x: c.x, y: c.y, z: c.z, colorscale: INFERNO_SCALE, connectgaps: false,
      contours: { coloring: "heatmap" }, colorbar: { title: { text: "Efficiency (%)" } },
      hovertemplate: "%{x} rpm, level %{y}: %{z:.1f} %<extra></extra>",
    } as Data,
    {
      type: "scatter", mode: "markers", showlegend: false, hoverinfo: "text",
      x: reached.map(([p]) => p.speed_rpm), y: reached.map(([, k]) => r.torque_fractions[k % nt]),
      customdata: reached.map(([, k]) => k), text: reached.map(([p]) => pointLabel(p)),
      marker: { color: reached.map(([, k]) => (k === sel ? LINE_COLORS[1] : LINE_COLORS[0])), size: reached.map(([, k]) => (k === sel ? 12 : 7)) },
    } as Data,
  ]
  const barData: Data[] = bars.series.map((s, i) => ({
    type: "bar", name: s.name, x: labels, y: s.values,
    marker: { color: LINE_COLORS[i], opacity: s.values.map((_, k) => (k === sel ? 1 : 0.45)) },
  })) as Data[]
  const axis = (text: string) => ({ ...theme.xaxis, title: { text } })
  const base = { ...theme, margin: { l: 60, r: 10, t: 10, b: 60 } }
  const cfg = { responsive: true, displaylogo: false }
  const sp = r.points[sel]
  const ratedP = rated >= 0 ? r.points[rated] : null

  return (
    <div className="space-y-6 pt-2">
      <div role="note" className="flex flex-wrap gap-2">
        {lossChips(r.winding_temperature_c).map((ch) => <Chip key={ch.text} {...ch} />)}
      </div>
      {r.notes.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {r.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
      <dl className="grid grid-cols-[auto_auto] justify-start gap-x-4 text-sm">
        <dt className="text-muted-foreground">Best efficiency</dt>
        <dd className="num">{best >= 0 ? `${fmt((r.points[best].efficiency ?? NaN) * 100, 3)} % at ${pointLabel(r.points[best])}` : "—"}</dd>
        <dt className="text-muted-foreground">Total loss at the rated point</dt>
        <dd className="num">{ratedP ? `${fmt(bars.totals[rated], 3)} W at ${pointLabel(ratedP)}` : "—"}</dd>
      </dl>
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-2">
          <h2 className={HEADING}>Efficiency over speed and torque level</h2>
          <Plot
            data={contour}
            layout={{ ...base, height: 340, xaxis: axis("Speed (rpm)"), yaxis: axis("Torque level (fraction of the envelope torque)") } as Partial<Layout>}
            config={cfg}
            onClick={(e) => {
              const k = (e.points?.[0] as { customdata?: unknown } | undefined)?.customdata
              if (typeof k === "number") setPicked(k)
            }}
          />
        </section>
        <section className="space-y-2">
          <h2 className={HEADING}>Loss split</h2>
          <Plot
            data={barData}
            layout={{ ...base, height: 340, barmode: "stack", xaxis: { ...axis(""), tickangle: -60 }, yaxis: axis("Loss (W)"), legend: { orientation: "h", y: -0.5 } } as Partial<Layout>}
            config={cfg}
          />
        </section>
      </div>
      <section className="space-y-3">
        <h2 className={HEADING}>Operating point</h2>
        <label className="flex items-center gap-2 text-sm">
          Point
          <select className={`${SELECT_CLASS} w-auto`} value={sel} onChange={(e) => setPicked(Number(e.target.value))}>
            {reached.map(([p, k]) => <option key={k} value={k}>{pointLabel(p)}</option>)}
          </select>
        </label>
        {sp?.reached && (
          <dl className="grid grid-cols-[auto_auto] justify-start gap-x-4 text-sm">
            <dt className="text-muted-foreground">Efficiency</dt>
            <dd className="num">{fmt((sp.efficiency ?? NaN) * 100, 3)} %</dd>
            <dt className="text-muted-foreground">Copper DC</dt>
            <dd className="num">{fmt(sp.copper_dc_w, 3)} W</dd>
            <dt className="text-muted-foreground">Copper AC</dt>
            <dd className="num">{sp.copper_ac_w == null ? "AC not computed (no wire chosen)" : `${fmt(sp.copper_ac_w, 3)} W`}</dd>
            <dt className="text-muted-foreground">Iron</dt>
            <dd className="num">{fmt(sp.iron_w, 3)} W</dd>
          </dl>
        )}
      </section>
      <section className="space-y-2">
        <h2 className={HEADING}>B(t) in an iron element</h2>
        {machine ? (
          <>
            <p className="text-sm text-muted-foreground">Click an iron element for the flux density in the stroke of the selected point.</p>
            <ElementPicker machine={machine} onPick={setAt} />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">The outline is not available.</p>
        )}
        {at && b.isPending && <SrmSpinner label="Looking up the element..." showLabel />}
        {b.isError && <p role="alert" className="text-sm text-destructive">{lossesMessage(b.error)}</p>}
        {b.data && (
          <>
            <LinePlot
              xTitle="Time (ms)"
              yTitle="B (T)"
              data={[
                { type: "scatter", mode: "lines", name: "B radial", x: b.data.t.map((v) => (v == null ? null : v * 1e3)), y: b.data.b_r, line: { color: LINE_COLORS[0], width: 2 }, connectgaps: false },
                { type: "scatter", mode: "lines", name: "B tangential", x: b.data.t.map((v) => (v == null ? null : v * 1e3)), y: b.data.b_t, line: { color: LINE_COLORS[1], width: 2, dash: "dash" }, connectgaps: false },
              ] as never}
            />
            <p className="text-sm text-muted-foreground">{b.data.side} {b.data.region.replace("_", " ")}</p>
          </>
        )}
      </section>
    </div>
  )
}

/** The steps of a running losses job; refreshes the stored result and the case once the job has ended. */
function RunningJob({ jobId, caseId, onEnded }: { jobId: string; caseId: string; onEnded: () => void }) {
  const qc = useQueryClient()
  const { job } = useJobEvents(jobId)
  const ended = !!job && !job.active
  useEffect(() => {
    if (!ended) return
    qc.invalidateQueries({ queryKey: ["losses", caseId] })
    qc.invalidateQueries({ queryKey: ["case", caseId] })
    onEnded()
  }, [ended, caseId, qc, onEnded])
  if (!job) return <SrmSpinner label="Starting..." showLabel />
  return (
    <>
      <JobStepper job={job} />
      {ended && job.status !== "done" && (
        <p role="alert" className="text-sm text-destructive">{job.error ?? `The losses job ${job.status}.`}</p>
      )}
    </>
  )
}

/** Efficiency and loss split of an evaluated case, and B(t) in a picked iron element. */
export default function LossesTab({ caseId }: { caseId: string }) {
  const c = useQuery({ queryKey: ["case", caseId], queryFn: () => api<Case>(`/api/cases/${caseId}`) })
  const losses = useLosses(caseId)
  const run = useRunLosses(caseId)
  const [started, setStarted] = useState<string | null>(null)
  const clearStarted = useCallback(() => setStarted(null), [])
  const jobId = c.data?.jobs.find((j) => j.kind === "losses" && j.active)?.id ?? started
  const estimate = useLossesEstimate(caseId, !losses.isPending && !losses.data)
  const machine = useMemo(() => (c.data?.inputs as { design?: { machine?: object } } | undefined)?.design?.machine, [c.data])

  if (losses.isPending) return <SrmSpinner className="py-4" label="Loading..." showLabel />
  return (
    <div className="space-y-4">
      {jobId && <div className="pt-2"><RunningJob jobId={jobId} caseId={caseId} onEnded={clearStarted} /></div>}
      {losses.data ? (
        <Results caseId={caseId} r={losses.data} machine={machine} />
      ) : (
        <p className="pt-2 text-sm text-muted-foreground">No losses for this case yet.</p>
      )}
      <div className="space-y-2">
        <Button
          type="button"
          variant={losses.data ? "outline" : "default"}
          className="min-h-11"
          disabled={run.isPending || !!jobId}
          onClick={() => run.mutate(undefined, { onSuccess: (r) => setStarted(r.job_id) })}
        >
          {losses.data ? "Run losses again" : "Run losses"}
        </Button>
        {estimate.data && !losses.data && (
          <p className="text-xs text-muted-foreground">
            {estimate.data.solves} solves, {fmtAbout(estimate.data.seconds)}
            {estimate.data.basis === "history" ? " (from recent runs)" : " (from the speed budget)"}.
          </p>
        )}
        {run.isError && <p role="alert" className="text-sm text-destructive">{lossesMessage(run.error)}</p>}
      </div>
    </div>
  )
}
