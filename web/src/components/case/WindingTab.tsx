import type { Num, WireForm } from "@/lib/searchForm"
import { cn } from "@/lib/utils"
import { Field, NumField, SELECT_CLASS, type TabProps } from "./fields"

const MODES = [["auto", "Auto"], ["fixed", "Fixed"]] as const
const KIND: Record<WireForm["kind"], string> = { round: "Round", rectangular: "Rectangular", litz: "Litz" }

const divisors = (n: number) => Array.from({ length: n }, (_, i) => i + 1).filter((d) => n % d === 0)

export function WindingTab({ form, update, errors }: TabProps) {
  const w = form.winding
  const set = (patch: Partial<typeof w>) => update((f) => ({ ...f, winding: { ...f.winding, ...patch } }))
  const poles = Number(form.machine.n_stator_poles)
  const phases = Number(form.machine.n_phases)
  const perPhase = poles / phases
  const options = Number.isInteger(perPhase) && perPhase > 0 ? divisors(perPhase) : [1]
  const paths = options.includes(Number(w.paths)) ? options : [...options, w.paths as Num]
  const density = w.wire === ""
  const wires = form.requirements.wires
  const wireLabel = (x: WireForm, i: number) => {
    const size = x.kind === "litz" ? x.strand_diameter : x.kind === "round" ? x.diameter : `${x.width}×${x.height}`
    return `Wire ${i + 1}: ${KIND[x.kind]} ${size} mm`
  }
  const j = (key: "jPeak" | "jLimit" | "jPeakMax", errKey: string, label: string, hint: string) => (
    <NumField id={errKey} label={label} unit="A/mm2" hint={hint} value={form[key]} error={errors[errKey]}
      onChange={(v) => update((f) => ({ ...f, [key]: v }))} />
  )

  return (
    <div className="space-y-6">
      <div role="radiogroup" aria-label="Winding mode" className="inline-flex rounded-[6px] border border-border-strong p-0.5">
        {MODES.map(([m, label]) => (
          <button key={m} type="button" role="radio" aria-checked={w.mode === m}
            onClick={() => set({ mode: m })}
            className={cn("min-h-11 rounded-[5px] px-4 text-[13px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              w.mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
            {label}
          </button>
        ))}
      </div>
      {w.mode === "auto" ? (
        <p className="text-sm text-muted-foreground">Auto picks the turns, paths and wire that the drive can carry.</p>
      ) : (
        <div className="grid gap-3.5">
          <NumField id="w-turns" label="Turns per pole" value={w.turns} error={errors["winding.turns"]}
            onChange={(v) => set({ turns: v })} />
          <NumField id="w-strands" label="Strands" value={density ? "1" : w.strands} error={errors["winding.strands"]}
            hint={density ? "Density mode has one strand." : undefined} disabled={density}
            onChange={(v) => set({ strands: v })} />
          <Field id="w-paths" label="Parallel paths" hint="Divisors of the poles per phase." error={errors["winding.paths"]}>
            {(aria) => (
              <select {...aria} className={SELECT_CLASS} value={String(w.paths)} onChange={(e) => set({ paths: e.target.value })}>
                {paths.map((p) => <option key={String(p)} value={String(p)}>{String(p)}</option>)}
              </select>
            )}
          </Field>
          <Field id="w-wire" label="Wire" error={errors["winding.wire"]}>
            {(aria) => (
              <select {...aria} className={SELECT_CLASS} value={String(w.wire)}
                onChange={(e) => set(e.target.value === "" ? { wire: "", strands: "1" } : { wire: e.target.value })}>
                <option value="">Density mode</option>
                {wires.map((x, i) => <option key={i} value={String(i)}>{wireLabel(x, i)}</option>)}
                {w.wire !== "" && Number(w.wire) >= wires.length && <option value={String(w.wire)}>Wire {Number(w.wire) + 1} (missing)</option>}
              </select>
            )}
          </Field>
        </div>
      )}
      <div className="grid gap-3.5">
        {j("jLimit", "j_limit", "RMS current density limit", "Empty takes the default.")}
        {j("jPeak", "j_peak", "Peak current density", "Empty takes the default.")}
        {j("jPeakMax", "j_peak_max", "Peak density cap", "Caps the map range. Empty means twice the RMS limit.")}
      </div>
    </div>
  )
}
