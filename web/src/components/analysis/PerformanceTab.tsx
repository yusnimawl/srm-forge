import { LinePlot } from "@/components/PlotlyPlot"
import { performanceSeries, type Overlay } from "@/lib/analysis"
import { UNIT_LABEL } from "@/lib/units"
import type { Evaluation } from "@/api/types"

export default function PerformanceTab({ evaluation, overlays, label }: { evaluation: Evaluation; overlays: Overlay[]; label?: string }) {
  const s = performanceSeries(evaluation, overlays, label)
  if (s.torque.length === 0) return <p className="py-4 text-sm text-muted-foreground">No performance data for this case.</p>
  const legend = s.torque.length > 1
  const x = "Speed (rpm)"
  return (
    <div className="grid gap-6 pt-2 lg:grid-cols-2">
      <LinePlot data={s.torque} legend={legend} xTitle={x} yTitle={`Torque (${UNIT_LABEL.Nm})`} />
      <LinePlot data={s.power} legend={legend} xTitle={x} yTitle={`Power (${UNIT_LABEL.kW})`} />
      <LinePlot data={s.efficiency} legend={legend} xTitle={x} yTitle={`Efficiency (${UNIT_LABEL["%"]})`} />
      <LinePlot data={s.current} legend={legend} xTitle={x} yTitle={`Phase current, RMS (${UNIT_LABEL.A})`} />
      <LinePlot data={s.lineCurrent} legend xTitle={x} yTitle={`Line current (${UNIT_LABEL.A})`} />
      <LinePlot data={s.powerFactor} legend={legend} xTitle={x} yTitle="Power factor" />
      <p className="text-sm text-muted-foreground lg:col-span-2">Efficiency and power factor count copper loss only.</p>
    </div>
  )
}
