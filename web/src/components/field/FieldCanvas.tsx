import { useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { buildScene, canRender, createGlRenderer, draw2d, viewMatrix, type Layers, type Renderer } from "@/lib/fieldGl"
import { pickTriangle } from "@/lib/fieldView"
import type { FieldFrameData, FieldMeshData } from "@/lib/fieldWire"

type View = { zoom: number; pan: [number, number] }
const HOME: View = { zoom: 1, pan: [0, 0] }
const MAX_ZOOM = 60

function hoverText(mesh: FieldMeshData, frame: FieldFrameData, t: number): string {
  const r = mesh.regions[mesh.region[t]]
  const where = r ? r.kind.replaceAll("_", " ") : "air gap"
  return `|B| ${(frame.b[t] ?? 0).toFixed(2)} T · ${where}`
}

/** The field of one frame: B per element, flux lines, mesh and region outlines. Wheel or pinch zooms, drag pans, arrow keys and +/- work too. */
export default function FieldCanvas({ mesh, frame, layers, bMax, onHover }: {
  mesh: FieldMeshData
  frame: FieldFrameData
  layers: Layers
  /** Fixed colour scale (T); default is the frame's own maximum. */
  bMax?: number
  onHover?: (text: string | null) => void
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  const renderer = useRef<Renderer | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  // A canvas that has held a webgl2 context cannot give a 2d one, so falling back remounts a fresh canvas.
  const [mode, setMode] = useState<{ gl: boolean; key: number }>(() => ({ gl: canRender() === "webgl2", key: 0 }))
  const [ready, setReady] = useState(false)
  const [view, setView] = useState<View>(HOME)
  const scene = useMemo(() => buildScene(mesh, frame, layers, bMax), [mesh, frame, layers, bMax])
  const m = useMemo(() => viewMatrix(scene.bounds, size.w || 1, size.h || 1, view.zoom, view.pan), [scene.bounds, size, view])

  useEffect(() => {
    const c = ref.current!
    const fallBack = () => setMode((o) => ({ gl: false, key: o.key + 1 }))
    renderer.current = mode.gl ? createGlRenderer(c, fallBack) : null
    if (mode.gl && !renderer.current) fallBack()
    setReady(true)
    const ro = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1
      const w = Math.max(1, Math.round(c.clientWidth * dpr))
      const h = Math.max(1, Math.round(c.clientHeight * dpr))
      c.width = w
      c.height = h
      setSize({ w, h })
    })
    ro.observe(c)
    return () => {
      ro.disconnect()
      renderer.current?.dispose()
      renderer.current = null
      setReady(false)
    }
  }, [mode])

  useEffect(() => {
    const c = ref.current!
    if (!ready || size.w === 0) return
    if (renderer.current) renderer.current.draw(scene, m, layers.bmap)
    else {
      const ctx = c.getContext("2d")
      if (ctx) draw2d(ctx, scene, m, size.w, size.h, layers.bmap)
    }
  }, [ready, scene, m, size, layers.bmap])

  const clipOf = (clientX: number, clientY: number): [number, number] => {
    const r = ref.current!.getBoundingClientRect()
    return [((clientX - r.left) / r.width) * 2 - 1, 1 - ((clientY - r.top) / r.height) * 2]
  }
  const zoomAt = (q: [number, number], factor: number) =>
    setView((v) => {
      const zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom * factor))
      const f = zoom / v.zoom
      return { zoom, pan: zoom === 1 ? [0, 0] : [q[0] - (q[0] - v.pan[0]) * f, q[1] - (q[1] - v.pan[1]) * f] }
    })

  useEffect(() => {
    const c = ref.current!
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomAt(clipOf(e.clientX, e.clientY), Math.exp(-e.deltaY * 0.002))
    }
    c.addEventListener("wheel", wheel, { passive: false })
    return () => c.removeEventListener("wheel", wheel)
  }, [])

  const pointers = useRef(new Map<number, [number, number]>())
  const pinch = useRef(0)
  const hoverAt = useRef<[number, number] | null>(null)
  const raf = useRef(0)
  useEffect(() => () => cancelAnimationFrame(raf.current), [])

  const dist = () => {
    const [a, b] = [...pointers.current.values()]
    return Math.hypot(a[0] - b[0], a[1] - b[1])
  }
  const hover = () => {
    raf.current = 0
    const p = hoverAt.current
    if (!p || !onHover) return
    const q = clipOf(p[0], p[1])
    const t = pickTriangle(scene.xy, scene.tris, (q[0] - m[6]) / m[0], (q[1] - m[7]) / m[4])
    onHover(t < 0 ? null : hoverText(mesh, frame, t))
  }

  return (
    <div className="relative">
      <canvas
        key={mode.key}
        ref={ref}
        tabIndex={0}
        role="img"
        aria-label="Magnetic field of the machine. Arrow keys pan, plus and minus zoom."
        className="aspect-square w-full touch-none rounded-[10px] border border-border bg-muted/30 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          pointers.current.set(e.pointerId, [e.clientX, e.clientY])
          if (pointers.current.size === 2) pinch.current = dist()
        }}
        onPointerMove={(e) => {
          const prev = pointers.current.get(e.pointerId)
          if (!prev) {
            hoverAt.current = [e.clientX, e.clientY]
            if (!raf.current) raf.current = requestAnimationFrame(hover)
            return
          }
          pointers.current.set(e.pointerId, [e.clientX, e.clientY])
          if (pointers.current.size === 2) {
            const d = dist()
            const [a, b] = [...pointers.current.values()]
            if (pinch.current > 0) zoomAt(clipOf((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), d / pinch.current)
            pinch.current = d
          } else if (pointers.current.size === 1) {
            const r = e.currentTarget.getBoundingClientRect()
            const dx = ((e.clientX - prev[0]) / r.width) * 2
            const dy = (-(e.clientY - prev[1]) / r.height) * 2
            setView((v) => ({ ...v, pan: [v.pan[0] + dx, v.pan[1] + dy] }))
          }
        }}
        onPointerUp={(e) => { pointers.current.delete(e.pointerId); pinch.current = 0 }}
        onPointerCancel={(e) => { pointers.current.delete(e.pointerId); pinch.current = 0 }}
        onPointerLeave={() => { hoverAt.current = null; onHover?.(null) }}
        onKeyDown={(e) => {
          const step = 0.1
          const pan = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key]
          if (pan) setView((v) => ({ ...v, pan: [v.pan[0] + pan[0], v.pan[1] + pan[1]] }))
          else if (e.key === "+" || e.key === "=") zoomAt([0, 0], 1.25)
          else if (e.key === "-") zoomAt([0, 0], 0.8)
          else return
          e.preventDefault()
        }}
      />
      <Button type="button" variant="outline" className="absolute right-2 top-2 min-h-11" onClick={() => setView(HOME)}>
        Reset view
      </Button>
    </div>
  )
}
