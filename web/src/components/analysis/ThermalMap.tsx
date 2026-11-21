import { useEffect, useMemo, useRef, useState } from "react"
import ColorBar from "@/components/field/ColorBar"
import { buildScalarScene, canRender, createGlRenderer, draw2d, viewMatrix, type Renderer } from "@/lib/fieldGl"
import { fetchThermalFields, type ThermalFieldsData } from "@/lib/thermalWire"

/** Temperature (°C) of the cross-section at one speed, steady or peak end; one colour scale over both states. */
export default function ThermalMap({ caseId, rpm, state, onSpeeds }: {
  caseId: string
  rpm: number
  state: "steady" | "peak"
  onSpeeds?: (rpm: number[]) => void
}) {
  const [data, setData] = useState<ThermalFieldsData | "gone" | "error" | null>(null)
  useEffect(() => {
    let live = true
    fetchThermalFields(caseId).then((d) => { if (live) { setData(d); if (d !== "gone") onSpeeds?.(d.rpm) } }, () => live && setData("error"))
    return () => { live = false }
  }, [caseId])
  if (data === "gone") return <p className="text-sm text-muted-foreground">Re-evaluate to see the map</p>
  if (data === "error") return <p className="text-sm text-muted-foreground">The temperature map could not be loaded</p>
  if (!data) return <p className="text-sm text-muted-foreground">Loading the temperature map</p>
  return <Map data={data} rpm={rpm} state={state} />
}

function Map({ data, rpm, state }: { data: ThermalFieldsData; rpm: number; state: "steady" | "peak" }) {
  const i = Math.max(0, data.rpm.indexOf(rpm))
  const [lo, hi] = useMemo(() => {
    let lo = Infinity, hi = -Infinity
    for (const v of [...data.steady[i], ...data.peak[i]]) if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v) }
    return hi > lo ? [lo, hi] : [0, 1]
  }, [data, i])
  const scene = useMemo(
    () => buildScalarScene(data.nodes, data.triangles, data.kind, data[state][i], lo, hi),
    [data, state, i, lo, hi],
  )
  const ref = useRef<HTMLCanvasElement>(null)
  const [gl] = useState(() => canRender() === "webgl2")
  useEffect(() => {
    const c = ref.current!
    const dpr = window.devicePixelRatio || 1
    c.width = Math.max(1, Math.round(c.clientWidth * dpr))
    c.height = Math.max(1, Math.round(c.clientHeight * dpr))
    const m = viewMatrix(scene.bounds, c.width, c.height, 1, [0, 0])
    const r: Renderer | null = gl ? createGlRenderer(c) : null
    if (r) { r.draw(scene, m, true); return () => r.dispose() }
    const ctx = gl ? null : c.getContext("2d")
    if (ctx) draw2d(ctx, scene, m, c.width, c.height, true)
  }, [scene, gl])
  return (
    <div className="flex gap-3">
      <canvas ref={ref} role="img" aria-label={`Temperature of the cross-section at ${rpm} r/min, ${state}`}
        className="aspect-square w-full max-w-md rounded-[10px] border border-border bg-muted/30" />
      <ColorBar bMax={hi} lo={lo} unit="°C" label="Temperature" />
    </div>
  )
}
