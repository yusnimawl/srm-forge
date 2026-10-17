import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useAnimate, useFrames } from "@/api/field"
import { api } from "@/api/client"
import type { Case } from "@/api/types"
import { useJobActions } from "@/api/useJobActions"
import { useJobEvents } from "@/api/useJobEvents"
import { LinePlot } from "@/components/PlotlyPlot"
import { Bar, fmtElapsed, progressOf } from "@/components/run/RunProgress"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { errorMessage } from "@/lib/errorMessage"
import { animateEstimate } from "@/lib/fieldView"
import type { FieldFrameData, FieldMeshData } from "@/lib/fieldWire"

/** The animation frame on screen, with the colour scale shared by all frames. */
export type AnimShown = { frame: FieldFrameData; bMax: number }
import { bMaxOfFrames } from "@/lib/fieldGl"
import { frameInterval, nextFrame, probeSeries, SPEEDS } from "@/lib/playback"

const FOCUS = "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"

/** Playback of the frames of one animate job once it is done; reports the shown frame through `onFrame`. */
function Playback({ jobId, mesh, onFrame, onActivate, pauseSignal }: {
  jobId: string
  mesh: FieldMeshData
  onFrame: (f: AnimShown | null) => void
  onActivate: () => void
  pauseSignal: number
}) {
  const { job } = useJobEvents(jobId)
  const actions = useJobActions()
  const done = job?.status === "done"
  const q = useFrames(done ? jobId : null)
  const frames = q.data?.frames
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)

  useEffect(() => {
    if (!frames || !playing) return
    const t = setInterval(() => setIdx((i) => nextFrame(i, frames.length)), frameInterval(speed))
    return () => clearInterval(t)
  }, [frames, playing, speed])
  const shown = frames?.[Math.min(idx, (frames?.length ?? 1) - 1)] ?? null
  const bMax = useMemo(() => (frames && mesh ? bMaxOfFrames(mesh, frames) : 0), [frames, mesh])
  // Playing, scrubbing or loading frames puts the animation on screen (onActivate); ticks only update the frame.
  useEffect(() => onFrame(shown && { frame: shown, bMax }), [shown, bMax, onFrame])
  const hasFrames = !!frames
  useEffect(() => {
    if (hasFrames) onActivate()
  }, [hasFrames, onActivate])
  // A new snapshot pauses playback so it stays on screen.
  useEffect(() => setPlaying(false), [pauseSignal])
  useEffect(() => () => onFrame(null), [onFrame])
  const series = useMemo(() => (frames ? probeSeries(frames, mesh.nRotorPoles) : []), [frames, mesh])

  if (!job) return <SrmSpinner label="Loading the animation..." showLabel />
  if (job.active) {
    const p = progressOf(job)
    return (
      <div className="space-y-2 rounded-[10px] border border-border bg-card p-3">
        <Bar label="Frames" done={p.points_done ?? 0} total={p.points_total ?? 0} />
        <div className="flex flex-wrap items-center gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Elapsed <span className="num">{fmtElapsed(p.elapsed_s)}</span>
            {p.message ? ` · ${p.message}` : ""}
          </p>
          <Button type="button" variant="outline" className="ml-auto min-h-11" disabled={actions.busy} onClick={() => actions.cancel(jobId)}>
            Cancel
          </Button>
        </div>
      </div>
    )
  }
  if (!done) return <p role="alert" className="text-sm text-destructive">{job.error ?? `The animation ${job.status}.`}</p>
  if (q.isPending) return <SrmSpinner label="Loading the frames..." showLabel />
  if (!frames || !shown) return <p role="alert" className="text-sm text-destructive">{errorMessage(q.error)}</p>

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" className="min-h-11 min-w-20" onClick={() => {
          if (!playing) onActivate()
          setPlaying((p) => !p)
        }}>
          {playing ? "Pause" : "Play"}
        </Button>
        <div className="flex items-center gap-2">
          <Label htmlFor="anim-speed">Speed</Label>
          <select
            id="anim-speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className={`min-h-11 rounded-[6px] border border-border-strong bg-background px-2 font-mono text-[13px] ${FOCUS}`}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{`${s}×`}</option>
            ))}
          </select>
        </div>
        <dl className="grid grid-cols-[auto_auto] gap-x-2 text-sm">
          <dt className="text-muted-foreground">Flux linkage (2D, no end winding)</dt>
          <dd className="font-mono">{(shown.psi * 1e3).toFixed(2)} mWb</dd>
          <dt className="text-muted-foreground">Torque</dt>
          <dd className="font-mono">{shown.torque.toFixed(2)} N·m</dd>
        </dl>
      </div>
      {shown.status === "NONCONVERGED" && (
        <p className="text-sm text-destructive">The solve did not converge; read this frame with care.</p>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="anim-frame">{`Frame ${idx + 1} of ${frames.length} at ${shown.currentA.toFixed(1)} A`}</Label>
        <input
          id="anim-frame"
          type="range"
          min={0}
          max={frames.length - 1}
          step={1}
          value={idx}
          onChange={(e) => {
            setPlaying(false)
            onActivate()
            setIdx(Number(e.target.value))
          }}
          className={`min-h-11 w-full accent-primary ${FOCUS}`}
        />
      </div>
      <div>
        <h3 className="text-sm font-medium">B in stator pole, yoke and rotor pole (T)</h3>
        <LinePlot data={series} xTitle="Electrical angle (°, from unaligned)" yTitle="|B| (T)" />
      </div>
    </div>
  )
}

/** Frame count, Animate stroke, and the playback of the running or loaded animation. */
export default function AnimationSection({ caseId, mesh, current, currentError, onFrame, onActivate, pauseSignal }: {
  caseId: string
  mesh: FieldMeshData
  current: number
  currentError?: string
  onFrame: (f: AnimShown | null) => void
  onActivate: () => void
  pauseSignal: number
}) {
  const [frames, setFrames] = useState("36")
  const [jobId, setJobId] = useState<string | null>(null)
  const animate = useAnimate(caseId)
  const c = useQuery({ queryKey: ["case", caseId], queryFn: () => api<Case>(`/api/cases/${caseId}`) })
  const last = (c.data?.jobs ?? [])
    .filter((j) => j.kind === "animate" && j.status === "done")
    .sort((a, b) => b.created.localeCompare(a.created))[0]
  const n = Number(frames)
  const framesError = !Number.isInteger(n) || n < 12 || n > 72 ? "Enter a whole number from 12 to 72." : undefined

  return (
    <section className="space-y-3 border-t border-border pt-4" aria-labelledby="anim-h">
      <h2 id="anim-h" className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Stroke animation</h2>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="anim-n">Frames</Label>
          <Input id="anim-n" inputMode="numeric" className="min-h-11 w-24 font-mono" value={frames}
            aria-invalid={!!framesError} aria-describedby="anim-note" onChange={(e) => setFrames(e.target.value)} />
        </div>
        <Button type="button" className="min-h-11" disabled={!!framesError || !!currentError || animate.isPending}
          onClick={() => animate.mutate({ current_a: current, frames: n }, { onSuccess: (r) => setJobId(r.job_id) })}>
          {animate.isPending ? "Starting..." : "Animate stroke"}
        </Button>
        {last && last.id !== jobId && (
          <Button type="button" variant="outline" className="min-h-11" onClick={() => setJobId(last.id)}>
            Load the last animation
          </Button>
        )}
      </div>
      <p id="anim-note" className={`text-xs ${framesError ? "text-destructive" : "text-muted-foreground"}`}>
        {framesError ?? `${animateEstimate(n)}, at the phase current above.`}
      </p>
      {animate.error && <p role="alert" className="rounded-[10px] border border-destructive p-3 text-sm text-destructive">{errorMessage(animate.error)}</p>}
      {jobId && <Playback key={jobId} jobId={jobId} mesh={mesh} onFrame={onFrame} onActivate={onActivate} pauseSignal={pauseSignal} />}
    </section>
  )
}
