import type { Evaluation } from "@/api/types"
import { fmt } from "@/lib/format"
import { NumField, type TabProps } from "./fields"

/** Bus voltage and phase current limit; the conduction angles the evaluation chose are read-only. */
export function DriveTab({ form, update, errors, evaluation }: TabProps & { evaluation: Evaluation | null }) {
  const r = form.requirements
  const set = (key: "busVoltageV" | "phaseCurrentA", value: string) =>
    update((f) => ({ ...f, requirements: { ...f.requirements, [key]: value } }))
  const env = evaluation?.envelope
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <NumField id="bus-voltage" label="Bus voltage" unit="V" value={r.busVoltageV} error={errors["requirements.bus_voltage_v"]}
          onChange={(v) => set("busVoltageV", v)} />
        <NumField id="phase-current" label="Phase current limit" unit="A" value={r.phaseCurrentA}
          error={errors["requirements.phase_current_a"]} hint="Inverter peak phase current. Empty means no limit."
          onChange={(v) => set("phaseCurrentA", v)} />
      </div>
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Conduction angles</h3>
        {env ? (
          <table className="w-full max-w-md text-sm">
            <caption className="pb-1 text-left text-xs text-muted-foreground">
              Electrical degrees, 0° = unaligned. Chosen by the evaluation.
            </caption>
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 font-medium">Speed (rpm)</th>
                <th className="py-1 font-medium">Turn-on (°)</th>
                <th className="py-1 font-medium">Turn-off (°)</th>
              </tr>
            </thead>
            <tbody>
              {env.speeds_rpm.map((s, i) => (
                <tr key={i} className="border-t">
                  <td className="num py-1">{fmt(s, 4)}</td>
                  <td className="num py-1">{fmt(env.theta_on_el[i], 4)}</td>
                  <td className="num py-1">{fmt(env.theta_off_el[i], 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground">The evaluation chooses them; evaluate the case to see them.</p>
        )}
      </div>
    </div>
  )
}
