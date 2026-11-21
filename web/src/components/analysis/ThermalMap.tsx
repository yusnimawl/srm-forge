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

const TOL = 0.5

function Map({ data, rpm, state }: { data: ThermalFieldsData; rpm: number; state: "steady" | "peak" }) {
  const i = data.rpm.findIndex((r) => Math.abs(r - rpm) <= TOL)
  const [lo, hi] = useMemo(() => {
    let lo = Infinity, hi = -Infinity
    for (const v of i < 0 ? [] : [...data.steady[i], ...data.peak[i]]) if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v) }
    return hi > lo ? [lo, hi] : [0, 1]
  }, [data, i])
  const scene = useMemo(
    () => (i < 0 ? null : buildScalarScene(data.nodes, data.triangles, data.kind, data[state][i], lo, hi)),
    [data, state, i, lo, hi],
  )
  const ref = useRef<HTMLCanvasElement>(null)
  const renderer = useRef<Renderer | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  // A canvas that has held a webgl2 context cannot give a 2d one, so falling back remounts a fresh canvas.
  const [mode, setMode] = useState<{ gl: boolean; key: number }>(() => ({ gl: canRender() === "webgl2", key: 0 }))
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const fallBack = () => setMode((o) => ({ gl: false, key: o.key + 1 }))
    renderer.current = mode.gl ? createGlRenderer(c, fallBack) : null
    if (mode.gl && !renderer.current) fallBack()
    setReady(true)
    const ro = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1
      c.width = Math.max(1, Math.round(c.clientWidth * dpr))
      c.height = Math.max(1, Math.round(c.clientHeight * dpr))
      setSize({ w: c.width, h: c.height })
    })
    ro.observe(c)
    return () => { ro.disconnect(); renderer.current?.dispose(); renderer.current = null; setReady(false) }
  }, [mode, i < 0])
  useEffect(() => {
    const c = ref.current
    if (!c || !scene || !ready || size.w === 0) return
    const m = viewMatrix(scene.bounds, size.w, size.h, 1, [0, 0])
    if (renderer.current) renderer.current.draw(scene, m, true)
    else {
      const ctx = c.getContext("2d")
      if (ctx) draw2d(ctx, scene, m, size.w, size.h, true)
    }
  }, [ready, scene, size])
  if (i < 0) return <p className="text-sm text-muted-foreground">No map for this speed</p>
  return (
    <div className="flex gap-3">
      <canvas key={mode.key} ref={ref} role="img" aria-label={`Temperature of the cross-section at ${rpm} r/min, ${state}`}
        className="aspect-square w-full max-w-md rounded-[10px] border border-border bg-muted/30" />
      <ColorBar bMax={hi} lo={lo} unit="°C" label="Temperature" />
    </div>
  )
}
