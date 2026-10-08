import { WireListEditor } from "@/components/search/WireListEditor"
import { withWires, type CaseForm } from "@/lib/caseForm"
import { NumField, type TabProps } from "./fields"

type Req = CaseForm["requirements"]

export function RequirementTab({ form, update, errors }: TabProps) {
  const r = form.requirements
  const set = <K extends keyof Req>(key: K, value: Req[K]) =>
    update((f) => ({ ...f, requirements: { ...f.requirements, [key]: value } }))
  const num = (key: Exclude<keyof Req, "wires">, errKey: string, id: string, label: string, unit?: "kW" | "Nm" | "rpm" | "mm" | "kg", hint?: string) => (
    <NumField id={id} label={label} unit={unit} hint={hint} error={errors[`requirements.${errKey}`]} value={r[key]}
      onChange={(v) => set(key, v)} />
  )
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        {num("peakPowerKw", "peak_power_w", "peak-power", "Peak power", "kW")}
        {num("peakTorqueNm", "peak_torque_nm", "peak-torque", "Peak torque", "Nm")}
        {num("baseSpeedRpm", "base_speed_rpm", "base-speed", "Base speed", "rpm")}
        {num("maxSpeedRpm", "max_speed_rpm", "max-speed", "Max speed", "rpm")}
        {num("maxOuterDiameterMm", "max_outer_diameter_m", "max-od", "Max outer diameter", "mm", "Empty means no limit.")}
        {num("maxMassKg", "max_mass_kg", "max-mass", "Max mass", "kg", "Empty means no limit.")}
        {num("maxSlotFill", "max_slot_fill", "slot-fill", "Max slot fill", undefined, "Outer wire area over coil-side area, up to 0.9.")}
      </div>
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Wires</h3>
        <WireListEditor wires={r.wires} onChange={(w) => update((f) => withWires(f, w))} errors={errors} />
      </div>
    </div>
  )
}
