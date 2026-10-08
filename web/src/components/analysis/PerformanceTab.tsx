import { LinePlot } from "@/components/PlotlyPlot"
import { performanceSeries, type Overlay } from "@/lib/analysis"
import { UNIT_LABEL } from "@/lib/units"
import type { Evaluation } from "@/api/types"

export default function PerformanceTab({ evaluation, overlays }: { evaluation: Evaluation; overlays: Overlay[] }) {
  if (!evaluation.envelope) return <p className="py-4 text-sm text-muted-foreground">No performance data for this case.</p>
  const s = performanceSeries(evaluation, overlays)
  const x = "Speed (rpm)"
  return (
    <div className="grid gap-6 pt-2 lg:grid-cols-2">
      <LinePlot data={s.torque} xTitle={x} yTitle={`Torque (${UNIT_LABEL.Nm})`} />
      <LinePlot data={s.power} xTitle={x} yTitle={`Power (${UNIT_LABEL.kW})`} />
      <LinePlot data={s.efficiency} xTitle={x} yTitle={`Efficiency (${UNIT_LABEL["%"]})`} />
      <LinePlot data={s.current} xTitle={x} yTitle={`Phase current, RMS (${UNIT_LABEL.A})`} />
      <p className="text-sm text-muted-foreground lg:col-span-2">Efficiency counts copper loss only.</p>
    </div>
  )
}
