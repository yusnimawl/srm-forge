import { useMemo } from "react"
import type { Data, Layout } from "plotly.js-dist-min"
import { Plot, useColors } from "@/components/PlotlyPlot"
import { fmt } from "@/lib/format"
import type { MapArrays } from "@/api/types"
import { pickAngles, psiCurves, torqueGrid } from "@/lib/mapCurves"

const DASH = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
const LINE_COLORS = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9"]

export default function MapCharts({ map, unaligned }: { map: MapArrays; unaligned: number | null }) {
  const c = useColors()
  const base = {
    autosize: true,
    height: 380,
    margin: { l: 60, r: 10, t: 10, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Fira Sans, sans-serif", color: c.fg },
  }
  const axis = (text: string) => ({ title: { text }, gridcolor: c.grid, color: c.fg })

  const lines = useMemo(() => {
    const all = psiCurves(map)
    return pickAngles(map.angles, unaligned).map((k, n) => ({
      type: "scatter",
      mode: "lines",
      name: `${fmt(all[k].angleDeg, 3)}°`,
      x: all[k].i,
      y: all[k].psi_mWb,
      line: { color: LINE_COLORS[n % 6], dash: DASH[n % 6], width: 2 },
    }))
  }, [map, unaligned])

  const grid = useMemo(() => torqueGrid(map), [map])
  const heat = [
    {
      type: "heatmap",
      x: grid.i,
      y: grid.angleDeg,
      z: grid.torque,
      colorscale: "Viridis",
      colorbar: { title: { text: "N·m", side: "right" } },
      hovertemplate: "i %{x:.3g} A<br>θ %{y:.3g}°<br>T %{z:.3g} N·m<extra></extra>",
    },
  ]
  const cfg = { responsive: true, displaylogo: false }
  return (
    <>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Flux linkage vs current</h2>
        <Plot
          data={lines as Data[]}
          layout={{ ...base, xaxis: axis("Current (A)"), yaxis: axis("ψ (mWb)"), legend: { title: { text: "Rotor angle" } } } as Partial<Layout>}
          config={cfg}
        />
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Torque map</h2>
        <Plot
          data={heat as Data[]}
          layout={{ ...base, xaxis: axis("Current (A)"), yaxis: axis("Rotor angle (° mechanical)") } as Partial<Layout>}
          config={cfg}
        />
      </section>
    </>
  )
}
