/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs"
import { join, relative } from "node:path"
import { describe, expect, it } from "vitest"

const ROOT = join(import.meta.dirname, "..")
const SKIP = join("api", "schema.ts")

const CLASS = /\b(blue|sky|indigo|cyan)-\d/
const HEX = /#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3})\b/gi
const FUNC = /\b(rgba?|hsla?)\(([^)]*)\)/gi
const NAMES = (
  "blue navy steelblue royalblue dodgerblue deepskyblue skyblue lightblue cornflowerblue midnightblue darkblue " +
  "mediumblue cadetblue powderblue lightskyblue aqua cyan teal slateblue darkslateblue mediumslateblue " +
  "lightsteelblue aliceblue"
).replace(/ /g, "|")
/** A blue CSS colour name as a whole word inside a string literal. */
const NAMED_IN_STRING = new RegExp(`(["'\`])(?:(?!\\1).)*\\b(?:${NAMES})\\b(?:(?!\\1).)*\\1`, "i")
/** A blue CSS colour name as a whole word in a declaration value. */
const NAMED_IN_CSS = new RegExp(`:[^;{}]*\\b(?:${NAMES})\\b`, "i")
/** A Plotly colour scale given by name; explicit arrays keep the scales checkable. */
const NAMED_SCALE = /\bcolorscale\s*:\s*["'`]/

/** Hue in degrees, saturation and lightness (0..1) of an sRGB colour (HSL model). */
function hsl(r: number, g: number, b: number): [number, number, number] {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const d = max - min
  const l = (max + min) / 2
  if (d === 0) return [0, 0, l]
  const s = d / (1 - Math.abs(2 * l - 1))
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  return [(h * 60 + 360) % 360, s, l]
}

/** Near-black colours (the first inferno stop) read as black whatever their hue. */
const isBlue = ([h, s, l]: [number, number, number]) => l >= 0.05 && h >= 190 && h <= 250 && s > 0.15

function hexBlue(hex: string): boolean {
  const h = hex.slice(1)
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255)
  return isBlue(hsl(r, g, b))
}

function funcBlue(name: string, args: string): boolean {
  const n = args.split(/[\s,/]+/).filter(Boolean).slice(0, 3).map((v) => parseFloat(v))
  if (n.length < 3 || n.some(Number.isNaN)) return false
  if (name.toLowerCase().startsWith("rgb")) return isBlue(hsl(n[0] / 255, n[1] / 255, n[2] / 255))
  return n[0] >= 190 && n[0] <= 250 && n[1] / 100 > 0.15 && n[2] / 100 >= 0.05
}

/** True when the text holds a blue class or a blue colour literal. */
export function blueIn(text: string, css = false): boolean {
  return (
    CLASS.test(text) ||
    NAMED_IN_STRING.test(text) ||
    NAMED_SCALE.test(text) ||
    (css && NAMED_IN_CSS.test(text)) ||
    (text.match(HEX) ?? []).some(hexBlue) ||
    [...text.matchAll(FUNC)].some((m) => funcBlue(m[1], m[2]))
  )
}

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? files(join(dir, e.name)) : [join(dir, e.name)],
  )
}

function offenders(): string[] {
  return files(ROOT)
    .filter((f) => relative(ROOT, f) !== SKIP && !f.endsWith("noBlue.test.ts"))
    .flatMap((f) =>
      readFileSync(f, "utf8")
        .split("\n")
        .flatMap((line, i) => (blueIn(line, f.endsWith(".css")) ? [`${relative(ROOT, f)}:${i + 1}: ${line.trim()}`] : [])),
    )
}

describe("no blue", () => {
  it("finds no blue", () => expect(offenders()).toEqual([]))
  it("flags a blue sample", () => {
    expect(blueIn("color: #2563EB")).toBe(true)
    expect(blueIn("bg-sky-500")).toBe(true)
    expect(blueIn("rgb(37, 99, 235)")).toBe(true)
    expect(blueIn("hsl(220 60% 50%)")).toBe(true)
  })
  it("flags short and alpha hex", () => {
    expect(blueIn("#36f")).toBe(true)
    expect(blueIn("#2563ebff")).toBe(true)
  })
  it("flags blue colour names in strings and css values", () => {
    expect(blueIn('color: "steelblue"')).toBe(true)
    expect(blueIn("const c = 'Teal'")).toBe(true)
    expect(blueIn("color: cyan;", true)).toBe(true)
    expect(blueIn("a { border: 1px solid aliceblue }", true)).toBe(true)
    expect(blueIn("// the bluebird sings")).toBe(false)
    expect(blueIn('"bluebird"')).toBe(false)
  })
  it("flags a named Plotly colour scale", () => {
    expect(blueIn('colorscale: "Viridis"')).toBe(true)
    expect(blueIn("colorscale: INFERNO_SCALE")).toBe(false)
    expect(blueIn("colorscale: [[0, '#000000'], [1, '#ffffff']]")).toBe(false)
  })
  it("ignores near-black colours", () => {
    expect(blueIn("rgb(0,0,4)")).toBe(false)
    expect(blueIn("#000004")).toBe(false)
    expect(blueIn("rgb(0,0,60)")).toBe(true)
  })
  it("passes greys and amber", () => expect(blueIn("#232323 #e8b04a #c3a6f0")).toBe(false))
})
