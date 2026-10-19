import { describe, expect, it } from "vitest"
import { PLAYER_SOURCE, PRINT_AXIS, PRINT_LINE_COLORS, SCREEN_AXIS, stepFrame, themeUpdate } from "./player"

describe("stepFrame", () => {
  it("wraps both ways", () => {
    expect(stepFrame(35, 36, 1)).toBe(0)
    expect(stepFrame(0, 36, -1)).toBe(35)
    expect(stepFrame(3, 36, 1)).toBe(4)
  })
})

describe("PLAYER_SOURCE", () => {
  it("is self-contained", () => {
    expect(PLAYER_SOURCE).not.toMatch(/\bimport\b|fetch|http/)
  })
  it("embeds a working stepFrame", () => {
    const m = /var stepFrame = (\(function[\s\S]*?\));\n/.exec(PLAYER_SOURCE)
    expect(m).not.toBeNull()
    const f = new Function(`return ${m![1]}`)() as typeof stepFrame
    expect(f(35, 36, 1)).toBe(0)
    expect(f(0, 36, -1)).toBe(35)
  })
  it("parses", () => {
    expect(() => new Function(PLAYER_SOURCE)).not.toThrow()
  })
})

describe("print theme", () => {
  it("lightens only the axes a layout has", () => {
    const u = themeUpdate({ xaxis: {}, yaxis: {} }, PRINT_AXIS)
    expect(u["xaxis.gridcolor"]).toBe(PRINT_AXIS.grid)
    expect(u["font.color"]).toBe("#333333")
    expect(Object.keys(u).some((k) => k.startsWith("yaxis2"))).toBe(false)
    expect(themeUpdate({ xaxis: {}, yaxis2: {} }, SCREEN_AXIS)["yaxis2.color"]).toBe(SCREEN_AXIS.font)
  })
  it("has a print colour per series colour, no hue of the screen palette", () => {
    expect(PRINT_LINE_COLORS).toHaveLength(7)
    PRINT_LINE_COLORS.forEach((c) => {
      const [r, g, b] = [1, 3, 5].map((k) => parseInt(c.slice(k, k + 2), 16))
      expect(b > r + 40 && b > g + 40).toBe(false)
    })
  })
  it("handles print events and guards JSON", () => {
    expect(PLAYER_SOURCE).toContain("beforeprint")
    expect(PLAYER_SOURCE).toContain("afterprint")
    expect(PLAYER_SOURCE).toMatch(/try \{ return JSON\.parse/)
  })
})

describe("print round trip", () => {
  it("restores the screen colours after printing", () => {
    const fig = { id: "p1", data: [{ type: "scatter", line: { color: "#e8b04a" } }, { type: "heatmap" }, { type: "bar", marker: { color: "#ededed" } }, { type: "scatter", mode: "markers", marker: { color: "#ededed", size: 7 } }], layout: { xaxis: {}, yaxis: {}, height: 360 } }
    const el = (id: string, text: string) => {
      const d = document.createElement("script")
      d.id = id
      d.textContent = text
      document.body.appendChild(d)
    }
    document.body.innerHTML = '<div class="grid two"><div id="p1"></div></div>'
    el("figures", JSON.stringify([fig]))
    // Like Plotly, newPlot keeps the array it is given and restyle changes it in place.
    const sizes: Record<string, unknown>[] = []
    let held: { type: string; line?: { color: string }; marker?: { color: string } }[] = []
    ;(window as unknown as { Plotly: unknown }).Plotly = {
      newPlot: (_id: string, data: typeof held) => { held = data },
      relayout: (_id: string, u: Record<string, unknown>) => { if ("width" in u) sizes.push(u) },
      restyle: (_id: string, u: Record<string, string>, idx: number[]) => {
        if (u["line.color"]) held[idx[0]].line!.color = u["line.color"]
        if (u["marker.color"]) held[idx[0]].marker!.color = u["marker.color"]
      },
    }
    new Function(PLAYER_SOURCE)()
    window.dispatchEvent(new Event("beforeprint"))
    expect(sizes[0]).toEqual({ autosize: false, width: 343, height: 260 })
    expect(held[0].line!.color).toBe(PRINT_LINE_COLORS[1])
    expect(held[2].marker!.color).toBe(PRINT_LINE_COLORS[0])
    expect(held[3].marker!.color).toBe(PRINT_LINE_COLORS[0])
    window.dispatchEvent(new Event("afterprint"))
    expect(sizes[1]).toEqual({ autosize: true, width: null, height: 360 })
    expect(held[0].line!.color).toBe("#e8b04a")
    expect(held[2].marker!.color).toBe("#ededed")
    expect(held[3].marker!.color).toBe("#ededed")
    window.dispatchEvent(new Event("beforeprint"))
    window.dispatchEvent(new Event("afterprint"))
    expect(held[0].line!.color).toBe("#e8b04a")
  })
})
