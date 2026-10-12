import { useMemo } from "react"
import type { Data, Layout } from "plotly.js-dist-min"
import { Plot, plotTheme, useColors } from "@/components/PlotlyPlot"
import { fmt } from "@/lib/format"
import { INFERNO_SCALE } from "@/lib/inferno"
import type { MapArrays } from "@/api/types"
import { caseLine } from "@/lib/analysis"
import { pickAngles, psiCurves, torqueGrid } from "@/lib/mapCurves"

export default function MapCharts({ map, unaligned }: { map: MapArrays; unaligned: number | null }) {
  const c = useColors()
  const base = { ...plotTheme(c), autosize: true, height: 380, margin: { l: 60, r: 10, t: 10, b: 50 } }
  const axis = (text: string) => ({ ...base.xaxis, title: { text } })

  const lines = useMemo(() => {
    const all = psiCurves(map)
    return pickAngles(map.angles, unaligned).map((k, n) => ({
      type: "scatter",
      mode: "lines",
      name: `${fmt(all[k].angleDeg, 3)}°`,
      x: all[k].i,
      y: all[k].psi_mWb,
      line: caseLine(n),
    }))
  }, [map, unaligned])

  const grid = useMemo(() => torqueGrid(map), [map])
  const heat = [
    {
      type: "heatmap",
      x: grid.i,
      y: grid.angleDeg,
      z: grid.torque,
      colorscale: INFERNO_SCALE,
      colorbar: { title: { text: "N·m", side: "right" } },
      hovertemplate: "i %{x:.3g} A<br>θ %{y:.3g}°<br>T %{z:.3g} N·m<extra></extra>",
    },
  ]
  const cfg = { responsive: true, displaylogo: false }
  return (
    <>
      <section className="space-y-2">
        <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Flux linkage vs current</h2>
        <Plot
          data={lines as Data[]}
          layout={{ ...base, xaxis: axis("Current (A)"), yaxis: axis("ψ (mWb)"), legend: { title: { text: "Rotor angle" } } } as Partial<Layout>}
          config={cfg}
        />
      </section>
      <section className="space-y-2">
        <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Torque map</h2>
        <Plot
          data={heat as Data[]}
          layout={{ ...base, xaxis: axis("Current (A)"), yaxis: axis("Rotor angle (° mechanical)") } as Partial<Layout>}
          config={cfg}
        />
      </section>
    </>
  )
}
