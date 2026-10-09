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

export function buildScene(mesh: FieldMeshData, frame: FieldFrameData, layers: Layers): Scene {
  const xy = positions(mesh, frame.angle)
  const tris = allTriangles(mesh, frame)
  const nt = tris.length / 3
  const bMax = bMaxOf(mesh, frame)
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
  if (layers.outlines) lines.push({ xy: edgeCoords(xy, regionEdges(tris, mesh.region)), color: OUTLINE })
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

/** WebGL2 renderer on `canvas`, or null when the context or the program is unavailable. */
export function createGlRenderer(canvas: HTMLCanvasElement): Renderer | null {
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: false })
  if (!gl) return null
  const shader = (type: number, src: string) => {
    const sh = gl.createShader(type)!
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null
  }
  const vs = shader(gl.VERTEX_SHADER, VS)
  const fs = shader(gl.FRAGMENT_SHADER, FS)
  if (!vs || !fs) return null
  const prog = gl.createProgram()!
  gl.attachShader(prog, vs)
  gl.attachShader(prog, fs)
  gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null
  const loc = {
    p: gl.getAttribLocation(prog, "p"),
    c: gl.getAttribLocation(prog, "c"),
    m: gl.getUniformLocation(prog, "m"),
    f: gl.getUniformLocation(prog, "flat_c"),
    u: gl.getUniformLocation(prog, "use_c"),
  }
  const vao = gl.createVertexArray()
  const bufs = [gl.createBuffer(), gl.createBuffer()]
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)

  const upload = (b: WebGLBuffer | null, data: Float32Array, attr: number, size: number) => {
    gl.bindBuffer(gl.ARRAY_BUFFER, b)
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(attr)
    gl.vertexAttribPointer(attr, size, gl.FLOAT, false, 0, 0)
  }
  return {
    draw(s, m, bmap) {
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.useProgram(prog)
      gl.bindVertexArray(vao)
      gl.uniformMatrix3fv(loc.m, false, m)
      if (bmap) {
        upload(bufs[0], s.triPos, loc.p, 2)
        upload(bufs[1], s.triRgb, loc.c, 3)
        gl.uniform1f(loc.u, 1)
        gl.drawArrays(gl.TRIANGLES, 0, s.triPos.length / 2)
      }
      gl.disableVertexAttribArray(loc.c)
      gl.vertexAttrib3f(loc.c, 0, 0, 0)
      gl.uniform1f(loc.u, 0)
      for (const l of s.lines) {
        upload(bufs[0], l.xy, loc.p, 2)
        gl.uniform4fv(loc.f, l.color)
        gl.drawArrays(gl.LINES, 0, l.xy.length / 2)
      }
    },
    dispose() {
      gl.getExtension("WEBGL_lose_context")?.loseContext()
    },
  }
}

export function canRender(): "webgl2" | "canvas2d" {
  try {
    return document.createElement("canvas").getContext("webgl2") ? "webgl2" : "canvas2d"
  } catch {
    return "canvas2d"
  }
}
