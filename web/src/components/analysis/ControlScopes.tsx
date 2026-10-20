import { useMemo } from "react"
import type { Data, Layout, PlotRelayoutEvent } from "plotly.js-dist-min"
import { Plot, plotTheme, useColors } from "@/components/PlotlyPlot"
import { LINE_COLORS } from "@/lib/analysis"
import { radSToRpm, type Channel, type ControlMeta } from "@/lib/control"

const MS = 1e3
const scaled = (c: Channel, fy = 1, fx = MS) => ({ x: c.t.map((v) => v * fx), y: c.y.map((v) => v * fy) })

const ROWS = ["Phase current (A)", "Flux linkage (mWb)", "Torque (N·m)", "Speed (rpm)", "Gates"]

/** Stacked scopes with a shared time axis: currents (true solid, ADC dotted), flux linkage, torque, speed, gates. */
export default function ControlScopes({ meta, channels, onZoom }: {
  meta: ControlMeta
  channels: Record<string, Channel>
  /** Called with true when the time axis is zoomed and false when it returns to the full range. */
  onZoom: (zoomed: boolean) => void
}) {
  const c = useColors()
  const traces = useMemo(() => {
    const out: Data[] = []
    const add = (row: number, name: string, ch: Channel | undefined, k: number, o: { dash?: string; width?: number; fy?: number; dy?: number; hv?: boolean; showlegend?: boolean } = {}) => {
      if (!ch) return
      const { x, y } = scaled(ch, o.fy)
      out.push({
        type: "scatter", mode: "lines", name, x: Array.from(x), y: Array.from(o.dy ? y.map((v) => v + o.dy!) : y),
        yaxis: row === 1 ? "y" : `y${row}`, xaxis: "x", showlegend: o.showlegend ?? true,
        line: { color: LINE_COLORS[k % LINE_COLORS.length], dash: o.dash ?? "solid", width: o.width ?? 1.5, shape: o.hv ? "hv" : "linear" },
      } as Data)
    }
    for (let k = 0; k < meta.n_phases; k++) {
      const ph = String.fromCharCode(65 + k)
      add(1, `i ${ph}`, channels[`i.${k}`], k)
      add(1, `ADC ${ph}`, channels[`adc_i.${k}`], k, { dash: "dot", width: 1 })
      add(2, `ψ ${ph}`, channels[`psi.${k}`], k, { fy: 1e3, showlegend: false })
      add(5, `gate upper ${ph}`, channels[`gate_u.${k}`], k, { hv: true, dy: k * 3 + 1.3, showlegend: false })
      add(5, `gate lower ${ph}`, channels[`gate_l.${k}`], k, { hv: true, dy: k * 3, dash: "dot", showlegend: false })
    }
    add(3, "torque", channels.torque, 0, { showlegend: false })
    add(4, "speed", channels.omega, 0, { fy: radSToRpm(1), showlegend: false })
    return out
  }, [meta.n_phases, channels])

  const theme = plotTheme(c)
  const gap = 0.035
  const h = (1 - gap * (ROWS.length - 1)) / ROWS.length
  const layout: Record<string, unknown> = {
    ...theme,
    height: 130 * ROWS.length + 70,
    margin: { l: 70, r: 10, t: 10, b: 45 },
    uirevision: "control",
    showlegend: true,
    legend: { orientation: "h", y: 1.04 },
    xaxis: { ...theme.xaxis, title: { text: "Time (ms)" }, anchor: "y5" },
  }
  ROWS.forEach((title, i) => {
    const top = 1 - i * (h + gap)
    layout[i === 0 ? "yaxis" : `yaxis${i + 1}`] = {
      ...theme.yaxis, title: { text: title }, domain: [top - h, top], anchor: "x",
      ...(i === 4 && { showticklabels: false, zeroline: false }),
    }
  })

  return (
    <Plot
      data={traces}
      layout={layout as Partial<Layout>}
      config={{ responsive: true, displaylogo: false }}
      onRelayout={(e: PlotRelayoutEvent) => {
        const ev = e as Record<string, unknown>
        if (ev["xaxis.range[0]"] !== undefined) onZoom(true)
        else if (ev["xaxis.autorange"]) onZoom(false)
      }}
    />
  )
}
