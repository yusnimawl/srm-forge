/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs"
import { join, relative } from "node:path"
import { describe, expect, it } from "vitest"

const ROOT = join(import.meta.dirname, "..")
const SKIP = join("api", "schema.ts")

const CLASS = /\b(blue|sky|indigo|cyan)-\d/
const HEX = /#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3})\b/gi
const FUNC = /\b(rgba?|hsla?)\(([^)]*)\)/gi

/** Hue in degrees and saturation 0..1 of an sRGB colour (HSL model). */
function hueSat(r: number, g: number, b: number): [number, number] {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const d = max - min
  if (d === 0) return [0, 0]
  const l = (max + min) / 2
  const s = d / (1 - Math.abs(2 * l - 1))
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  return [(h * 60 + 360) % 360, s]
}

const isBlue = ([h, s]: [number, number]) => h >= 190 && h <= 250 && s > 0.15

function hexBlue(hex: string): boolean {
  const h = hex.slice(1)
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255)
  return isBlue(hueSat(r, g, b))
}

function funcBlue(name: string, args: string): boolean {
  const n = args.split(/[\s,/]+/).filter(Boolean).slice(0, 3).map((v) => parseFloat(v))
  if (n.length < 3 || n.some(Number.isNaN)) return false
  if (name.toLowerCase().startsWith("rgb")) return isBlue(hueSat(n[0] / 255, n[1] / 255, n[2] / 255))
  return n[0] >= 190 && n[0] <= 250 && n[1] / 100 > 0.15
}

/** True when the text holds a blue class or a blue colour literal. */
export function blueIn(text: string): boolean {
  return (
    CLASS.test(text) ||
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
        .flatMap((line, i) => (blueIn(line) ? [`${relative(ROOT, f)}:${i + 1}: ${line.trim()}`] : [])),
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
  it("passes greys and amber", () => expect(blueIn("#232323 #e8b04a #c3a6f0")).toBe(false))
})
