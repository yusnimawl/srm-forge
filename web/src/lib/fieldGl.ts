import { contourLevels, contourSegments } from "./contours"
import { allTriangles, positions, regionEdges } from "./fieldView"
import type { FieldFrameData, FieldMeshData } from "./fieldWire"
import { viridis } from "./viridis"

export type Bounds = { minX: number; minY: number; maxX: number; maxY: number }
export type Layers = { bmap: boolean; flux: boolean; mesh: boolean; outlines: boolean }
type Rgba = [number, number, number, number]

/** Column-major 3x3 view matrix: the bounds fitted to the canvas (aspect ratio kept), scaled by `zoom`, then shifted by `pan` in clip units. */
export function viewMatrix(b: Bounds, width: number, height: number, zoom: number, pan: [number, number]): Float32Array {
  const k = Math.min(width / (b.maxX - b.minX), height / (b.maxY - b.minY)) * zoom
  const sx = (2 * k) / width
  const sy = (2 * k) / height
  const cx = (b.minX + b.maxX) / 2
  const cy = (b.minY + b.maxY) / 2
  return new Float32Array([sx, 0, 0, 0, sy, 0, pan[0] - sx * cx, pan[1] - sy * cy, 1])
}

export function boundsOf(xy: Float32Array): Bounds {
  const b = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }
  for (let i = 0; i < xy.length; i += 2) {
    b.minX = Math.min(b.minX, xy[i]); b.maxX = Math.max(b.maxX, xy[i])
    b.minY = Math.min(b.minY, xy[i + 1]); b.maxY = Math.max(b.maxY, xy[i + 1])
  }
  return b
}

export const bMaxOf = (mesh: FieldMeshData, frame: FieldFrameData): number => {
  let m = mesh.bLast
  for (const v of frame.b) if (v > m) m = v
  return m
}

/** One |B| scale for a whole set of frames, so colours compare across them. */
export const bMaxOfFrames = (mesh: FieldMeshData, frames: FieldFrameData[]): number =>
  frames.reduce((m, f) => Math.max(m, bMaxOf(mesh, f)), mesh.bLast)

// Region edges of the static triangles are the same at every angle: the band's boundary edges are boundary edges of the static mesh.
const staticEdges = new WeakMap<FieldMeshData, Uint32Array>()
function regionEdgesOf(mesh: FieldMeshData): Uint32Array {
  let e = staticEdges.get(mesh)
  if (!e) staticEdges.set(mesh, (e = regionEdges(mesh.triangles, mesh.region)))
  return e
}

/** Everything a renderer draws, in world metres. */
export type Scene = {
  xy: Float32Array
  tris: Uint32Array
  /** Triangles expanded to 3 vertices: x, y per vertex, and r, g, b (0..1) per vertex. */
  triPos: Float32Array
  triRgb: Float32Array
  lines: { xy: Float32Array; color: Rgba }[]
  bounds: Bounds
  bMax: number
}

// Line colours are data: they must read on every viridis shade.
const WIRE: Rgba = [0, 0, 0, 0.25]
const OUTLINE: Rgba = [0, 0, 0, 0.9]
const FLUX: Rgba = [1, 1, 1, 0.9]

function edgeCoords(xy: Float32Array, idx: Uint32Array): Float32Array {
  const out = new Float32Array(idx.length * 2)
  for (let i = 0; i < idx.length; i++) { out[2 * i] = xy[2 * idx[i]]; out[2 * i + 1] = xy[2 * idx[i] + 1] }
  return out
}

/** `bMaxOverride` fixes the colour scale; by default it is the frame's own maximum. */
export function buildScene(mesh: FieldMeshData, frame: FieldFrameData, layers: Layers, bMaxOverride?: number): Scene {
  const xy = positions(mesh, frame.angle)
  const tris = allTriangles(mesh, frame)
  const nt = tris.length / 3
  const bMax = bMaxOverride ?? bMaxOf(mesh, frame)
  const triPos = new Float32Array(nt * 6)
  const triRgb = new Float32Array(nt * 9)
  for (let t = 0; t < nt; t++) {
    const [r, g, b] = viridis((frame.b[t] ?? 0) / bMax)
    for (let k = 0; k < 3; k++) {
      const n = tris[3 * t + k]
      triPos[6 * t + 2 * k] = xy[2 * n]
      triPos[6 * t + 2 * k + 1] = xy[2 * n + 1]
      triRgb.set([r / 255, g / 255, b / 255], 9 * t + 3 * k)
    }
  }
  const lines: Scene["lines"] = []
  if (layers.mesh) {
    const e = new Uint32Array(nt * 6)
    for (let t = 0; t < nt; t++) for (let k = 0; k < 3; k++) { e[6 * t + 2 * k] = tris[3 * t + k]; e[6 * t + 2 * k + 1] = tris[3 * t + ((k + 1) % 3)] }
    lines.push({ xy: edgeCoords(xy, e), color: WIRE })
  }
  if (layers.flux) lines.push({ xy: contourSegments(xy, tris, frame.a, contourLevels(frame.a)), color: FLUX })
  if (layers.outlines) lines.push({ xy: edgeCoords(xy, regionEdgesOf(mesh)), color: OUTLINE })
  return { xy, tris, triPos, triRgb, lines, bounds: boundsOf(xy), bMax }
}

/** The 2D fallback: the same colours and lines on a CanvasRenderingContext2D. */
export function draw2d(ctx: CanvasRenderingContext2D, s: Scene, m: Float32Array, w: number, h: number, bmap: boolean) {
  ctx.clearRect(0, 0, w, h)
  const px = (x: number, y: number): [number, number] => [((m[0] * x + m[6] + 1) / 2) * w, ((1 - (m[4] * y + m[7])) / 2) * h]
  if (bmap) {
    ctx.lineWidth = 0.5
    for (let t = 0; t < s.triPos.length / 6; t++) {
      ctx.beginPath()
      for (let k = 0; k < 3; k++) {
        const [x, y] = px(s.triPos[6 * t + 2 * k], s.triPos[6 * t + 2 * k + 1])
        if (k === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      const o = 9 * t
      const css = `rgb(${(s.triRgb[o] * 255) | 0},${(s.triRgb[o + 1] * 255) | 0},${(s.triRgb[o + 2] * 255) | 0})`
      ctx.fillStyle = css
      ctx.strokeStyle = css // hides hairline gaps between neighbours
      ctx.fill()
      ctx.stroke()
    }
  }
  ctx.lineWidth = 1
  for (const l of s.lines) {
    ctx.strokeStyle = `rgba(${l.color[0] * 255},${l.color[1] * 255},${l.color[2] * 255},${l.color[3]})`
    ctx.beginPath()
    for (let i = 0; i < l.xy.length; i += 4) {
      const [x0, y0] = px(l.xy[i], l.xy[i + 1])
      const [x1, y1] = px(l.xy[i + 2], l.xy[i + 3])
      ctx.moveTo(x0, y0)
      ctx.lineTo(x1, y1)
    }
    ctx.stroke()
  }
}

const VS = `#version 300 es
in vec2 p; in vec3 c; uniform mat3 m; out vec3 vc;
void main(){ vc = c; gl_Position = vec4((m * vec3(p, 1.0)).xy, 0.0, 1.0); }`
const FS = `#version 300 es
precision mediump float; in vec3 vc; uniform vec4 flat_c; uniform float use_c; out vec4 o;
void main(){ o = use_c > 0.5 ? vec4(vc, 1.0) : flat_c; }`

export type Renderer = { draw: (s: Scene, m: Float32Array, bmap: boolean) => void; dispose: () => void }

/** WebGL2 renderer on `canvas`, or null when the context or the program is unavailable. `onLost` is called when the context is dropped. */
export function createGlRenderer(canvas: HTMLCanvasElement, onLost?: () => void): Renderer | null {
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: false })
  if (!gl) return null
  const prog = gl.createProgram()
  const vs = gl.createShader(gl.VERTEX_SHADER)
  const fs = gl.createShader(gl.FRAGMENT_SHADER)
  const buffers: (WebGLBuffer | null)[] = []
  const release = () => {
    buffers.forEach((b) => gl.deleteBuffer(b))
    gl.deleteProgram(prog)
    gl.deleteShader(vs)
    gl.deleteShader(fs)
  }
  if (!prog || !vs || !fs) { release(); return null }
  for (const [sh, src] of [[vs, VS], [fs, FS]] as const) {
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    gl.attachShader(prog, sh)
  }
  gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { release(); return null }
  const loc = {
    p: gl.getAttribLocation(prog, "p"),
    c: gl.getAttribLocation(prog, "c"),
    m: gl.getUniformLocation(prog, "m"),
    f: gl.getUniformLocation(prog, "flat_c"),
    u: gl.getUniformLocation(prog, "use_c"),
  }
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
  const lost = (e: Event) => { e.preventDefault(); onLost?.() }
  canvas.addEventListener("webglcontextlost", lost)

  // One vertex array per layer, filled once per scene; a draw only sets the view uniform.
  type Layer = { vao: WebGLVertexArrayObject; n: number }
  const layer = (data: Float32Array, size: number, extra?: Float32Array): Layer => {
    const v = gl.createVertexArray()!
    gl.bindVertexArray(v)
    const put = (d: Float32Array, attr: number, sz: number) => {
      const b = gl.createBuffer()
      buffers.push(b)
      gl.bindBuffer(gl.ARRAY_BUFFER, b)
      gl.bufferData(gl.ARRAY_BUFFER, d, gl.STATIC_DRAW)
      gl.enableVertexAttribArray(attr)
      gl.vertexAttribPointer(attr, sz, gl.FLOAT, false, 0, 0)
    }
    put(data, loc.p, size)
    if (extra) put(extra, loc.c, 3)
    else gl.vertexAttrib3f(loc.c, 0, 0, 0)
    return { vao: v, n: data.length / size }
  }
  let uploaded: Scene | null = null
  let tri: Layer | null = null
  let lines: Layer[] = []
  const vaos: WebGLVertexArrayObject[] = []
  const drop = () => {
    vaos.forEach((v) => gl.deleteVertexArray(v))
    vaos.length = 0
    buffers.forEach((b) => gl.deleteBuffer(b))
    buffers.length = 0
  }
  const upload = (s: Scene) => {
    drop()
    tri = layer(s.triPos, 2, s.triRgb)
    lines = s.lines.map((l) => layer(l.xy, 2))
    vaos.push(tri.vao, ...lines.map((l) => l.vao))
    uploaded = s
  }
  return {
    draw(s, m, bmap) {
      if (s !== uploaded) upload(s)
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.useProgram(prog)
      gl.uniformMatrix3fv(loc.m, false, m)
      if (bmap && tri) {
        gl.uniform1f(loc.u, 1)
        gl.bindVertexArray(tri.vao)
        gl.drawArrays(gl.TRIANGLES, 0, tri.n)
      }
      gl.uniform1f(loc.u, 0)
      lines.forEach((l, i) => {
        gl.uniform4fv(loc.f, s.lines[i].color)
        gl.bindVertexArray(l.vao)
        gl.drawArrays(gl.LINES, 0, l.n)
      })
    },
    dispose() {
      canvas.removeEventListener("webglcontextlost", lost)
      drop()
      release()
    },
  }
}

export function canRender(): "webgl2" | "canvas2d" {
  try {
    const gl = document.createElement("canvas").getContext("webgl2")
    gl?.getExtension("WEBGL_lose_context")?.loseContext()
    return gl ? "webgl2" : "canvas2d"
  } catch {
    return "canvas2d"
  }
}
