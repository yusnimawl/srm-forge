import { useState } from "react"
import { LinePlot } from "@/components/PlotlyPlot"
import { defaultSpeedIndex, waveformSeries } from "@/lib/waveforms"
import { UNIT_LABEL } from "@/lib/units"
import type { Evaluation } from "@/api/types"

const X = "Rotor angle (° electrical, 0 = unaligned)"

export default function WaveformsTab({ evaluation, baseSpeedRpm }: { evaluation: Evaluation; baseSpeedRpm?: number }) {
  const [picked, setPicked] = useState<number | null>(null)
  const speeds = evaluation.envelope?.speeds_rpm ?? []
  const k = picked ?? defaultSpeedIndex(evaluation, baseSpeedRpm)
  const s = waveformSeries(evaluation, k)
  if (!s) return <p className="py-4 text-sm text-muted-foreground">No waveforms for this case.</p>
  return (
    <div className="space-y-4 pt-2">
      <label className="flex items-center gap-2 text-sm">
        Speed
        <select
          className="min-h-11 rounded-md border border-input bg-background px-3"
          value={k}
          onChange={(e) => setPicked(Number(e.target.value))}
        >
          {speeds.map((v, i) => (
            <option key={i} value={i}>{`${v ?? "?"} rpm`}</option>
          ))}
        </select>
      </label>
      <div className="grid gap-6 lg:grid-cols-2">
        <LinePlot data={s.current} legend={false} xTitle={X} yTitle={`Phase current (${UNIT_LABEL.A})`} />
        <LinePlot data={s.psi} legend={false} xTitle={X} yTitle={`Flux linkage (${UNIT_LABEL.mWb})`} />
        <LinePlot data={s.voltage} legend={false} xTitle={X} yTitle={`Phase voltage (${UNIT_LABEL.V})`} />
        <LinePlot data={s.torque} legend={false} xTitle={X} yTitle={`Phase torque (${UNIT_LABEL.Nm})`} />
        <LinePlot data={s.line} legend={false} xTitle={X} yTitle={`Line current (${UNIT_LABEL.A})`} />
        <LinePlot data={s.loop} xTitle={`Current (${UNIT_LABEL.A})`} yTitle={`Flux linkage (${UNIT_LABEL.mWb})`} />
      </div>
      <p className="text-sm text-muted-foreground">Phase A over one rotor pole pitch; line current sums all phases. Peak-only drive model.</p>
    </div>
  )
}
