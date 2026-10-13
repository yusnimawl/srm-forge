import { MACHINE_FIELDS, POLE_KEYS, POLE_SETS } from "@/lib/caseForm"
import { Field, NumField, SELECT_CLASS, type TabProps } from "./fields"

export function DimensionTab({ form, update, errors }: TabProps) {
  const m = form.machine
  const current = POLE_KEYS.map((k) => String(m[k])).join("/")
  const sets = POLE_SETS.map((s) => s.join("/"))
  const options = sets.includes(current) || POLE_KEYS.some((k) => m[k] === "") ? sets : [...sets, current]
  const poleError = POLE_KEYS.map((k) => errors[`design.machine.${k}`]).find(Boolean)

  const setPoles = (value: string) => {
    const [s, r, p] = value.split("/")
    update((f) => ({ ...f, machine: { ...f.machine, n_stator_poles: s, n_rotor_poles: r, n_phases: p } }))
  }
  const label = (s: string) => {
    const [a, b, p] = s.split("/")
    return `${a}/${b} · ${p}-phase`
  }

  return (
    <div className="grid gap-3.5">
      <Field id="pole-set" label="Pole set" hint="Stator/rotor poles and phases." error={poleError}>
        {(aria) => (
          <select {...aria} className={SELECT_CLASS} value={options.includes(current) ? current : ""}
            onChange={(e) => setPoles(e.target.value)}>
            {!options.includes(current) && <option value="">Choose a pole set</option>}
            {options.map((s) => <option key={s} value={s}>{label(s)}</option>)}
          </select>
        )}
      </Field>
      <Field id="preset" label="Preset" error={errors["design.mesh.preset"]}
        hint="Screening is quicker and less accurate; results show their preset.">
        {(aria) => (
          <select {...aria} className={SELECT_CLASS} value={form.preset}
            onChange={(e) => update((f) => ({ ...f, preset: e.target.value as typeof form.preset }))}>
            <option value="full">Full</option>
            <option value="screening">Screening</option>
          </select>
        )}
      </Field>
      {MACHINE_FIELDS.map((f) => (
        <NumField key={f.key} id={`m-${f.key}`} label={f.label} unit={f.unit} hint={f.hint} value={m[f.key]}
          error={errors[`design.machine.${f.key}`]}
          onChange={(v) => update((old) => ({ ...old, machine: { ...old.machine, [f.key]: v } }))} />
      ))}
    </div>
  )
}
