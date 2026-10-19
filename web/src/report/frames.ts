import { bMaxOfFrames, boundsOf, buildScene, createGlRenderer, draw2d, viewMatrix } from "@/lib/fieldGl"
import type { FieldFrameData, FieldMeshData } from "@/lib/fieldWire"

const LAYERS = { bmap: true, flux: false, mesh: false, outlines: true }

const canvasOf = (size: number) => {
  const c = document.createElement("canvas")
  c.width = c.height = size
  return c
}

/** Renders each frame offscreen (the |B| map on one colour scale for all frames) and returns data URIs: WebP where the browser encodes it, else PNG. */
export async function renderFrames(
  mesh: FieldMeshData,
  frames: FieldFrameData[],
  onFrame: (k: number, n: number) => void,
  size = 640,
): Promise<string[]> {
  let canvas = canvasOf(size)
  const gl = createGlRenderer(canvas)
  let ctx: CanvasRenderingContext2D | null = null
  if (!gl) {
    // A canvas that held a webgl2 context cannot give a 2d one, so the fallback uses a fresh canvas.
    canvas = canvasOf(size)
    ctx = canvas.getContext("2d")
    if (!ctx) throw new Error("no canvas renderer")
  }
  const bMax = bMaxOfFrames(mesh, frames)
  const m = viewMatrix(boundsOf(mesh.nodes), size, size, 1, [0, 0])
  const out: string[] = []
  try {
    for (const [k, frame] of frames.entries()) {
      const scene = buildScene(mesh, frame, LAYERS, bMax)
      if (gl) gl.draw(scene, m, true)
      else draw2d(ctx!, scene, m, size, size, true)
      let uri = canvas.toDataURL("image/webp", 0.85)
      if (!uri.startsWith("data:image/webp")) uri = canvas.toDataURL("image/png")
      out.push(uri)
      onFrame(k + 1, frames.length)
      await new Promise((r) => setTimeout(r)) // let the progress toast repaint
    }
  } finally {
    gl?.dispose()
  }
  return out
}
