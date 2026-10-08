import type { Data, Layout } from "plotly.js-dist-min"
import { Plot, useColors } from "@/components/PlotlyPlot"
import { fmt } from "@/lib/format"
import { fromSI, UNIT_LABEL } from "@/lib/units"
import type { Envelope } from "@/api/types"

export default function EnvelopeChart({ envelope }: { envelope: Envelope }) {
  const c = useColors()
  const e = envelope
  // θ = 0° electrical is the unaligned position.
  const hover = e.speeds_rpm.map(
    (_, k) => `turn-on ${fmt(e.theta_on_el[k])}° el, turn-off ${fmt(e.theta_off_el[k])}° el`,
  )
  const trace = (name: string, y: (number | null)[], color: string, yaxis: string, dash: string) => ({
    type: "scatter",
    mode: "lines+markers",
    name,
    x: e.speeds_rpm,
    y,
    yaxis,
    line: { color, dash },
    text: hover,
    hovertemplate: `%{x:.0f} rpm, ${name} %{y:.4g}<br>%{text}<extra></extra>`,
    connectgaps: false,
  })
  const axis = (text: string, extra = {}) => ({ title: { text }, gridcolor: c.grid, color: c.fg, ...extra })
  const layout = {
    autosize: true,
    height: 380,
    margin: { l: 60, r: 60, t: 10, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Fira Sans, sans-serif", color: c.fg },
    xaxis: axis("Speed (rpm)"),
    yaxis: axis("Torque (N·m)"),
    yaxis2: axis(`Power (${UNIT_LABEL.kW})`, { overlaying: "y", side: "right", showgrid: false }),
    legend: { orientation: "h", y: -0.2 },
  }
  return (
    <Plot
      data={[trace("torque", e.torque, "#0072b2", "y", "solid"), trace("power", e.power.map((w) => (w == null ? null : fromSI(w, "kW"))), "#d55e00", "y2", "dash")] as Data[]}
      layout={layout as Partial<Layout>}
      config={{ responsive: true, displaylogo: false }}
    />
  )
}
