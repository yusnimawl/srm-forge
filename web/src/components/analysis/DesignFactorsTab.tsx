import { LinePlot } from "@/components/PlotlyPlot"
import { designFactorTraces, MAIN_LABEL, type Overlay } from "@/lib/analysis"
import { UNIT_LABEL } from "@/lib/units"
import type { Evaluation } from "@/api/types"

export default function DesignFactorsTab({ evaluation, overlays, label = MAIN_LABEL }: { evaluation: Evaluation; overlays: Overlay[]; label?: string }) {
  if (!evaluation.curves) return <p className="py-4 text-sm text-muted-foreground">No design factors for this case.</p>
  const d = designFactorTraces([
    { label, curves: evaluation.curves },
    ...overlays.map((o) => ({ label: o.label, curves: o.evaluation.curves })),
  ])
  return (
    <div className="grid gap-6 pt-2 lg:grid-cols-2">
      <section className="space-y-2">
        <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Inductance vs current</h2>
        <LinePlot data={d.inductance} xTitle={`Current (${UNIT_LABEL.A})`} yTitle={`L (${UNIT_LABEL.mH})`} />
      </section>
      <section className="space-y-2">
        <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">k2 and pole flux density vs current</h2>
        <LinePlot data={d.factors} xTitle={`Current (${UNIT_LABEL.A})`} yTitle="k2" y2Title={`B_sp (${UNIT_LABEL.T})`} />
      </section>
      <section className="space-y-2">
        <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">B_sp·k2 vs La_sat/Lu</h2>
        <LinePlot data={d.bspK2VsRatio} legend={d.bspK2VsRatio.length > 1} xTitle="La_sat / Lu" yTitle={`B_sp·k2 (${UNIT_LABEL.T})`} />
      </section>
      <p className="self-end text-sm text-muted-foreground">k2 = 1 − Lu/La_sat (Krishnan ch. 3); efficiency copper only</p>
    </div>
  )
}
