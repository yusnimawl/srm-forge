import { boundsOf, buildScalarScene, buildScene, createGlRenderer, draw2d, viewMatrix, type Scene } from "@/lib/fieldGl"
import type { FieldFrameData, FieldMeshData } from "@/lib/fieldWire"
import type { ThermalFieldsData } from "@/lib/thermalWire"

const LAYERS = { bmap: true, flux: false, mesh: false, outlines: true }

const canvasOf = (size: number) => {
  const c = document.createElement("canvas")
  c.width = c.height = size
  return c
}

/** Draws each scene offscreen, WebGL where available else 2D, and returns data URIs: WebP where the browser encodes it, else PNG. */
async function renderScenes(scenes: Iterable<Scene>, count: number, onFrame: (k: number, n: number) => void, size: number): Promise<string[]> {
  let canvas = canvasOf(size)
  const gl = createGlRenderer(canvas)
  let ctx: CanvasRenderingContext2D | null = null
  if (!gl) {
    // A canvas that held a webgl2 context cannot give a 2d one, so the fallback uses a fresh canvas.
    canvas = canvasOf(size)
    ctx = canvas.getContext("2d")
    if (!ctx) throw new Error("no canvas renderer")
  }
  const out: string[] = []
  try {
    for (const scene of scenes) {
      const m = viewMatrix(boundsOf(scene.xy), size, size, 1, [0, 0])
      if (gl) gl.draw(scene, m, true)
      else draw2d(ctx!, scene, m, size, size, true)
      let uri = canvas.toDataURL("image/webp", 0.85)
      if (!uri.startsWith("data:image/webp")) uri = canvas.toDataURL("image/png")
      out.push(uri)
      onFrame(out.length, count)
      await new Promise((r) => setTimeout(r)) // let the progress toast repaint
    }
  } finally {
    gl?.dispose()
  }
  return out
}

/** Renders each frame offscreen (the |B| map on the colour scale `bMax`). */
export function renderFrames(
  mesh: FieldMeshData,
  frames: FieldFrameData[],
  bMax: number,
  onFrame: (k: number, n: number) => void,
  size = 640,
): Promise<string[]> {
  return renderScenes((function* () { for (const f of frames) yield buildScene(mesh, f, LAYERS, bMax) })(), frames.length, onFrame, size)
}

/** One temperature map (inferno between `lo` and `hi`) as a data URI. */
export async function renderThermalMap(data: ThermalFieldsData, values: Float32Array, lo: number, hi: number, size = 640): Promise<string> {
  const [uri] = await renderScenes([buildScalarScene(data.nodes, data.triangles, data.kind, values, lo, hi)], 1, () => {}, size)
  return uri
}
