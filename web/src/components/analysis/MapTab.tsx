import { LinePlot } from "@/components/PlotlyPlot"
import MapCharts from "@/components/candidate/MapCharts"
import { inductanceCurves, torqueCurves } from "@/lib/analysis"
import type { Evaluation } from "@/api/types"

export default function MapTab({ evaluation }: { evaluation: Evaluation }) {
  const { map, curves } = evaluation
  if (!map) return <p className="py-4 text-sm text-muted-foreground">No map for this case.</p>
  return (
    <div className="grid gap-6 pt-2 lg:grid-cols-2">
      <MapCharts map={map} unaligned={evaluation.key?.unaligned_angle ?? null} />
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Torque vs rotor angle</h2>
        <LinePlot data={torqueCurves(map)} xTitle="Rotor angle (° mechanical)" yTitle="Torque (N·m)" />
      </section>
      {curves && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Inductance vs rotor angle</h2>
          <LinePlot data={inductanceCurves(curves, map.angles)} xTitle="Rotor angle (° mechanical)" yTitle="L = ψ/i (mH)" />
        </section>
      )}
    </div>
  )
}
