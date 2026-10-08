import { LinePlot } from "@/components/PlotlyPlot"
import { designFactorTraces, MAIN_LABEL, type Overlay } from "@/lib/analysis"
import type { Evaluation } from "@/api/types"

export default function DesignFactorsTab({ evaluation, overlays }: { evaluation: Evaluation; overlays: Overlay[] }) {
  if (!evaluation.curves) return <p className="py-4 text-sm text-muted-foreground">No design factors for this case.</p>
  const d = designFactorTraces([
    { label: MAIN_LABEL, curves: evaluation.curves },
    ...overlays.map((o) => ({ label: o.label, curves: o.evaluation.curves })),
  ])
  return (
    <div className="grid gap-6 pt-2 lg:grid-cols-2">
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Inductance vs current</h2>
        <LinePlot data={d.inductance} xTitle="Current (A)" yTitle="L (mH)" />
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">k2 and pole flux density vs current</h2>
        <LinePlot data={d.factors} xTitle="Current (A)" yTitle="k2" y2Title="B_sp (T)" />
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">B_sp·k2 vs La_sat/Lu</h2>
        <LinePlot data={d.bspK2VsRatio} xTitle="La_sat / Lu" yTitle="B_sp·k2 (T)" />
      </section>
      <p className="self-end text-sm text-muted-foreground">k2 = 1 − Lu/La_sat (Krishnan ch. 3); efficiency copper only</p>
    </div>
  )
}
