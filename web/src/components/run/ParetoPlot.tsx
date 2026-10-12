import { useEffect, useMemo, useState } from "react"
import type { Data, Layout } from "plotly.js-dist-min"
import { Plot, plotTheme, useColors } from "@/components/PlotlyPlot"
import { useNavigate } from "react-router"
import { AXES, type AxisKey, type CandidateRow } from "@/lib/candidates"

const SYMBOLS = ["circle", "square", "diamond", "triangle-up"]
// scatter3d has no triangle marker
const SYMBOLS_3D = ["circle", "square", "diamond", "cross"]
const KEYS = Object.keys(AXES) as AxisKey[]
const SELECT_CLASS =
  "min-h-11 rounded-lg border border-input bg-input/30 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

function useMedia(query: string) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setMatch(m.matches)
    m.addEventListener("change", on)
    return () => m.removeEventListener("change", on)
  }, [query])
  return match
}

function AxisSelect({ label, value, onChange }: { label: string; value: AxisKey; onChange: (k: AxisKey) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      {label}
      <select className={SELECT_CLASS} value={value} onChange={(e) => onChange(e.target.value as AxisKey)}>
        {KEYS.map((k) => (
          <option key={k} value={k}>
            {AXES[k]}
          </option>
        ))}
      </select>
    </label>
  )
}

export default function ParetoPlot({ rows }: { rows: CandidateRow[] }) {
  const navigate = useNavigate()
  const wide = useMedia("(min-width: 1024px)")
  const c = useColors()
  const [x, setX] = useState<AxisKey>("mass_kg")
  const [y, setY] = useState<AxisKey>("power_density")
  const [z, setZ] = useState<AxisKey>("peak_power_kw")
  const [three, setThree] = useState(false)
  const is3d = three && wide

  const pole = useMemo(() => [...new Set(rows.map((r) => r.poles))].sort(), [rows])

  const data = useMemo(() => {
    const eff = rows.map((r) => r.efficiency_base).filter((v): v is number => v != null)
    const cmin = Math.min(...eff)
    const cmax = Math.max(...eff)
    const type = is3d ? "scatter3d" : "scatter"
    const traces: Record<string, unknown>[] = []
    const coord = (rs: CandidateRow[]) => ({
      x: rs.map((r) => r[x]),
      y: rs.map((r) => r[y]),
      ...(is3d ? { z: rs.map((r) => r[z]) } : {}),
      customdata: rs.map((r) => r.id),
      text: rs.map((r) => `${r.id} · ${r.poles}${r.pareto ? " · Pareto" : ""}`),
      hoverinfo: "text+x+y",
    })
    let colorbarShown = false
    pole.forEach((p, i) => {
      const symbol = (is3d ? SYMBOLS_3D : SYMBOLS)[i % 4]
      const group = rows.filter((r) => r.poles === p)
      const good = group.filter((r) => r.feasible && r.efficiency_base != null)
      const bad = group.filter((r) => !(r.feasible && r.efficiency_base != null))
      if (good.length) {
        traces.push({
          ...coord(good),
          type,
          mode: "markers",
          name: p,
          legendgroup: p,
          marker: {
            symbol,
            size: 10,
            color: good.map((r) => r.efficiency_base),
            colorscale: "Inferno",
            cmin,
            cmax,
            showscale: !colorbarShown,
            colorbar: { title: { text: "Efficiency at base speed", side: "right" }, tickfont: { color: c.faint } },
            line: {
              color: good.map((r) => (r.pareto ? c.primary : "rgba(0,0,0,0)")),
              width: good.map((r) => (r.pareto ? 3 : 0)),
            },
          },
        })
        colorbarShown = true
      }
      if (bad.length)
        traces.push({
          ...coord(bad),
          type,
          mode: "markers",
          name: `${p} infeasible / failed`,
          legendgroup: p,
          showlegend: !good.length,
          marker: { symbol: is3d ? symbol : symbol + "-open", size: 9, color: c.muted, line: { color: c.muted, width: 1.5 } },
        })
    })
    return traces
  }, [rows, pole, x, y, z, is3d, c])

  const theme = plotTheme(c)
  const axis = (k: AxisKey) => ({ ...theme.xaxis, title: { text: AXES[k] } })
  const layout = {
    ...theme,
    autosize: true,
    height: 460,
    margin: { l: 60, r: 10, t: 10, b: 50 },
    legend: { orientation: "h", y: -0.2 },
    ...(is3d ? { scene: { xaxis: axis(x), yaxis: axis(y), zaxis: axis(z) } } : { xaxis: axis(x), yaxis: axis(y) }),
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <AxisSelect label="X" value={x} onChange={setX} />
        <AxisSelect label="Y" value={y} onChange={setY} />
        {is3d && <AxisSelect label="Z" value={z} onChange={setZ} />}
        {wide && (
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={three} onChange={(e) => setThree(e.target.checked)} />
            3D
          </label>
        )}
      </div>
      <Plot
        data={data as Data[]}
        layout={layout as Partial<Layout>}
        config={{ responsive: true, displaylogo: false }}
        onClick={(e) => {
          const id = e.points[0]?.customdata
          if (typeof id === "string") navigate(`${location.pathname}/candidates/${encodeURIComponent(id)}`)
        }}
      />
      <p className="text-sm text-muted-foreground">
        X: {AXES[x]} · Y: {AXES[y]}
        {is3d ? ` · Z: ${AXES[z]}` : ""} · colour: efficiency at base speed · marker: pole set ({pole.join(", ")}) ·
        outlined: Pareto set · grey hollow: infeasible or failed
      </p>
    </div>
  )
}
