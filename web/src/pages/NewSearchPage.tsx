import { useState, type FormEvent, type ReactNode } from "react"
import { useNavigate } from "react-router"
import { useQuery } from "@tanstack/react-query"
import { api, ApiError, submitSearch, type Material } from "@/api/client"
import { WireListEditor } from "@/components/search/WireListEditor"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { defaultSearchForm, fieldErrors, toSearchRequest, validateForm, type SearchFormValues } from "@/lib/searchForm"
import { UNIT_LABEL, type Unit } from "@/lib/units"
import { cn } from "@/lib/utils"

const QUEUE_FULL = "Queue full — wait for a run to finish"
const SELECT_CLASS =
  "min-h-11 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"

// Errors shown under a field; every other key goes to the summary.
const FIELD_KEYS = new Set([
  ...["peak_power_w", "peak_torque_nm", "base_speed_rpm", "max_speed_rpm", "bus_voltage_v", "max_outer_diameter_m",
    "max_mass_kg", "max_slot_fill", "phase_current_a"].map((k) => `requirements.${k}`),
  ...["n_candidates", "shortlist", "seed", "stator", "rotor", "preset"].map((k) => `settings.${k}`),
])

type Aria = { id: string; "aria-invalid": boolean; "aria-describedby"?: string }

function Field({ id, label, unit, hint, error, children }: {
  id: string
  label: string
  unit?: string
  hint?: string
  error?: string
  children: (aria: Aria) => ReactNode
}) {
  const described = [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(" ") || undefined
  const unitText = unit && (unit in UNIT_LABEL ? UNIT_LABEL[unit as Unit] : unit)
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        {children({ id, "aria-invalid": !!error, "aria-describedby": described })}
        {unitText && <span className="w-12 shrink-0 text-sm text-muted-foreground">{unitText}</span>}
      </div>
      {hint && <p id={`${id}-hint`} className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p id={`${id}-err`} className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

export function NewSearchPage() {
  const [v, setV] = useState<SearchFormValues>(defaultSearchForm)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const materials = useQuery({ queryKey: ["materials"], queryFn: () => api<Material[]>("/api/materials") })

  const set = <K extends keyof SearchFormValues>(key: K, value: SearchFormValues[K]) =>
    setV((old) => ({ ...old, [key]: value }))

  const num = (key: keyof SearchFormValues, errKey: string, id: string, label: string, unit?: string, hint?: string) => (
    <Field id={id} label={label} unit={unit} hint={hint} error={errors[errKey]}>
      {(aria) => (
        <Input {...aria} inputMode="decimal" className="min-h-11 font-mono" value={String(v[key])}
          onChange={(e) => set(key, e.target.value as never)} />
      )}
    </Field>
  )

  async function submit(e: FormEvent) {
    e.preventDefault()
    const invalid = validateForm(v)
    setErrors(invalid)
    if (Object.keys(invalid).length > 0) return
    setBusy(true)
    try {
      const { id } = await submitSearch(toSearchRequest(v))
      navigate(`/runs/${id}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setErrors({ "": QUEUE_FULL })
      else if (err instanceof ApiError) setErrors(fieldErrors(err.detail))
      else setErrors({ "": "Could not reach the server. Try again." })
    } finally {
      setBusy(false)
    }
  }

  const summary = Object.entries(errors).filter(([k]) => !FIELD_KEYS.has(k) && !/^requirements\.wires\.\d/.test(k))

  const materialSelect = (key: "stator" | "rotor", label: string) => {
    const m = materials.data?.find((x) => x.name === v[key])
    return (
      <Field id={key} label={label} error={errors[`settings.${key}`]}>
        {(aria) => (
          <>
            <select {...aria} className={SELECT_CLASS} value={v[key]} onChange={(e) => set(key, e.target.value)}>
              {(materials.data ?? [{ name: v[key] }]).map((x) => (
                <option key={x.name} value={x.name}>{x.name}</option>
              ))}
            </select>
            {m && <Badge variant="secondary" className="shrink-0">Grade {m.grade}</Badge>}
          </>
        )}
      </Field>
    )
  }

  return (
    <form onSubmit={submit} noValidate className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold text-primary">New search</h1>

      {summary.length > 0 && (
        <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <p className="font-medium">Check the form:</p>
          <ul className="list-disc pl-5">
            {summary.map(([k, msg]) => <li key={k}>{k ? `${k}: ${msg}` : msg}</li>)}
          </ul>
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Requirements</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {num("peakPowerKw", "requirements.peak_power_w", "peak-power", "Peak power", "kW")}
          {num("peakTorqueNm", "requirements.peak_torque_nm", "peak-torque", "Peak torque", "Nm")}
          {num("baseSpeedRpm", "requirements.base_speed_rpm", "base-speed", "Base speed", "rpm")}
          {num("maxSpeedRpm", "requirements.max_speed_rpm", "max-speed", "Max speed", "rpm")}
          {num("busVoltageV", "requirements.bus_voltage_v", "bus-voltage", "Bus voltage", "V")}
          {num("maxOuterDiameterMm", "requirements.max_outer_diameter_m", "max-od", "Max outer diameter", "mm", "Empty means no limit.")}
          {num("maxMassKg", "requirements.max_mass_kg", "max-mass", "Max mass", "kg", "Empty means no limit.")}
          {num("maxSlotFill", "requirements.max_slot_fill", "slot-fill", "Max slot fill", "ratio", "Outer wire area over coil-side area, up to 0.9.")}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Winding</CardTitle>
          <CardDescription>Density mode sizes the turns from current density. Wire mode uses your wires and inverter current.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div role="radiogroup" aria-label="Winding mode" className="inline-flex rounded-lg border p-0.5">
            {(["density", "wires"] as const).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={v.windingMode === m}
                onClick={() => set("windingMode", m)}
                className={cn("min-h-11 rounded-md px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  v.windingMode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
                {m === "density" ? "Density" : "Wire list"}
              </button>
            ))}
          </div>
          {v.windingMode === "wires" && (
            <>
              <div className="max-w-sm">
                {num("phaseCurrentA", "requirements.phase_current_a", "phase-current", "Phase current (peak)", "A", "Inverter peak phase current.")}
              </div>
              <WireListEditor wires={v.wires} onChange={(w) => set("wires", w)} errors={errors} />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Search</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {num("nCandidates", "settings.n_candidates", "n-candidates", "Candidates", undefined, "1 to 2000.")}
          {num("shortlist", "settings.shortlist", "shortlist", "Shortlist", undefined, "1 to 200.")}
          {num("seed", "settings.seed", "seed", "Seed")}
          <div />
          {materialSelect("stator", "Stator material")}
          {materialSelect("rotor", "Rotor material")}
          <Field id="preset" label="Preset" error={errors["settings.preset"]}
            hint="Screening is quicker and less accurate; results show their preset.">
            {(aria) => (
              <select {...aria} className={SELECT_CLASS} value={v.preset}
                onChange={(e) => set("preset", e.target.value as SearchFormValues["preset"])}>
                <option value="full">Full</option>
                <option value="screening">Screening</option>
              </select>
            )}
          </Field>
        </CardContent>
      </Card>

      <Button type="submit" disabled={busy} className="min-h-11 px-6">{busy ? "Starting…" : "Start search"}</Button>
    </form>
  )
}
