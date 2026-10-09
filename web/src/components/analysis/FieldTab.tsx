import { useCallback, useMemo, useState } from "react"
import { useFieldMesh, useFieldSnapshot } from "@/api/field"
import { ApiError } from "@/api/client"
import AnimationSection, { type AnimShown } from "./AnimationSection"
import ColorBar from "@/components/field/ColorBar"
import FieldCanvas from "@/components/field/FieldCanvas"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { errorMessage } from "@/lib/errorMessage"
import { bMaxOf, canRender, type Layers } from "@/lib/fieldGl"
import { electricalDeg } from "@/lib/fieldView"
import type { FieldFrameData } from "@/lib/fieldWire"

const LAYER_LABELS: [keyof Layers, string][] = [
  ["bmap", "|B| map"],
  ["flux", "Flux lines"],
  ["mesh", "Mesh"],
  ["outlines", "Region outlines"],
]
const RAD = Math.PI / 180

function detail(e: unknown): string {
  return e instanceof ApiError && typeof e.detail === "string" ? e.detail : errorMessage(e)
}

/** Snapshots of the field of an evaluated case at one rotor angle and phase current. */
export default function FieldTab({ caseId }: { caseId: string }) {
  const meshQ = useFieldMesh(caseId)
  const snap = useFieldSnapshot(caseId)
  const [layers, setLayers] = useState<Layers>({ bmap: true, flux: true, mesh: false, outlines: true })
  const [deg, setDeg] = useState(0)
  const [current, setCurrent] = useState<string | null>(null)
  // The last frame stays on screen while the next one solves, so the canvas (and its zoom) persists.
  const [frame, setFrame] = useState<FieldFrameData | null>(null)
  // While an animation is shown its frame replaces the snapshot; the canvas stays mounted.
  const [anim, setAnim] = useState<AnimShown | null>(null)
  const [source, setSource] = useState<"snap" | "anim">("snap")
  const onAnimFrame = useCallback((f: AnimShown | null) => {
    setAnim(f)
    if (f) setSource("anim")
  }, [])
  const [hover, setHover] = useState<string | null>(null)
  const mesh = meshQ.data
  const shown = source === "anim" && anim ? anim.frame : frame
  const shownBMax = source === "anim" && anim ? anim.bMax : undefined
  const renderMode = useMemo(canRender, [])

  if (meshQ.isPending) return <p className="py-4 text-sm text-muted-foreground">Loading the field mesh...</p>
  if (!mesh) return <p role="alert" className="py-4 text-sm text-destructive">{detail(meshQ.error)}</p>

  const pitchDeg = 360 / mesh.nRotorPoles
  const wrap = (rad: number) => ((((rad / RAD) % pitchDeg) + pitchDeg) % pitchDeg)
  const amps = current ?? mesh.windingCurrent.toFixed(1)
  const a = Number(amps)
  const tooHigh = a > 2 * mesh.iMax
  const currentError = amps.trim() === "" || !Number.isFinite(a) ? "Enter a current in A." : tooHigh ? `At most ${(2 * mesh.iMax).toFixed(1)} A (twice the map's top current).` : undefined

  return (
    <div className="@container space-y-4 pt-2">
      {renderMode === "canvas2d" && (
        <p className="text-sm text-muted-foreground">This browser has no WebGL2: snapshots only, no animation.</p>
      )}
      <div className="space-y-4">
        <div className="space-y-2">
          {shown ? (
            <div className="flex flex-col gap-3 @2xl:flex-row @2xl:items-start">
              <div className="mx-auto w-full min-w-0 max-w-[70vh] flex-1">
                <FieldCanvas mesh={mesh} frame={shown} layers={layers} bMax={shownBMax} onHover={setHover} />
              </div>
              <ColorBar bMax={shownBMax ?? bMaxOf(mesh, shown)} bLast={mesh.bLast} />
            </div>
          ) : (
            <div className="mx-auto grid aspect-square w-full max-w-[70vh] place-items-center rounded-lg border border-border bg-muted/30 p-4 text-center text-sm text-muted-foreground">
              {snap.isPending ? "Solving..." : "Choose an angle and a current, then press Show."}
            </div>
          )}
          <p className="min-h-6 text-sm" aria-live="polite">{hover ?? " "}</p>
        </div>
        <div className="grid gap-4 @2xl:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="field-angle">Rotor angle</Label>
            <input
              id="field-angle"
              type="range"
              min={0}
              max={pitchDeg}
              step={0.25}
              value={deg}
              onChange={(e) => setDeg(Number(e.target.value))}
              className="min-h-11 w-full accent-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <p className="text-sm">{`${deg.toFixed(2)}° mech (${electricalDeg(deg * RAD, mesh.nRotorPoles).toFixed(1)}° el)`}</p>
            <div className="flex gap-2">
              <Button type="button" variant="outline" className="min-h-11" onClick={() => setDeg(wrap(mesh.alignedAngle))}>Aligned</Button>
              <Button type="button" variant="outline" className="min-h-11" onClick={() => setDeg(wrap(mesh.unalignedAngle))}>Unaligned</Button>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="field-current">Phase current (A)</Label>
            <Input id="field-current" inputMode="decimal" className="min-h-11 font-mono" value={amps}
              aria-invalid={!!currentError} aria-describedby={currentError ? "field-current-err" : undefined}
              onChange={(e) => setCurrent(e.target.value)} />
            {currentError && <p id="field-current-err" className="text-sm text-destructive">{currentError}</p>}
          </div>
          <Button type="button" className="min-h-11" disabled={!!currentError || snap.isPending}
            onClick={() => snap.mutate({ angle: deg * RAD, current_a: a }, { onSuccess: (f) => { setFrame(f); setSource("snap") } })}>
            {snap.isPending ? "Solving..." : "Show"}
          </Button>
          <p className="text-xs text-muted-foreground">First view about 10 s (mesh + one solve); repeats are instant from the cache.</p>
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">Layers</legend>
            {LAYER_LABELS.map(([k, text]) => (
              <label key={k} className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" className="size-5 accent-primary" checked={layers[k]}
                  onChange={(e) => setLayers((l) => ({ ...l, [k]: e.target.checked }))} />
                {text}
              </label>
            ))}
          </fieldset>
          {shown && (
            <dl className="grid grid-cols-2 gap-1 text-sm">
              <dt className="text-muted-foreground">Flux linkage</dt>
              <dd className="font-mono">{(shown.psi * 1e3).toFixed(2)} mWb</dd>
              <dt className="text-muted-foreground">Torque</dt>
              <dd className="font-mono">{shown.torque.toFixed(2)} N·m</dd>
            </dl>
          )}
          {source === "snap" && shown?.status === "NONCONVERGED" && (
            <p className="text-sm text-destructive">The solve did not converge; read this frame with care.</p>
          )}
          {snap.error && <p role="alert" className="rounded-lg border border-destructive p-3 text-sm text-destructive">{detail(snap.error)}</p>}
        </div>
      </div>
      {renderMode === "webgl2" && (
        <AnimationSection caseId={caseId} mesh={mesh} current={a} currentError={currentError} onFrame={onAnimFrame} />
      )}
    </div>
  )
}
