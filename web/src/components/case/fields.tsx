import type { ReactNode } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { CaseForm } from "@/lib/caseForm"
import { UNIT_LABEL, type Unit } from "@/lib/units"

export const SELECT_CLASS =
  "min-h-11 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30"

/** What every input tab gets: the form, an updater, and the validation errors by dotted field name. */
export type TabProps = {
  form: CaseForm
  update: (fn: (f: CaseForm) => CaseForm) => void
  errors: Record<string, string>
  /** The feasibility margin the server resolved for the inputs (null while unknown). */
  margin?: number | null
}

export type Aria = { id: string; "aria-invalid": boolean; "aria-describedby"?: string }

export function Field({ id, label, unit, hint, error, children }: {
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

export function NumField({ id, label, unit, hint, error, value, onChange, disabled }: {
  id: string
  label: string
  unit?: string
  hint?: string
  error?: string
  value: string | number
  onChange: (value: string) => void
  disabled?: boolean
}) {
  return (
    <Field id={id} label={label} unit={unit} hint={hint} error={error}>
      {(aria) => (
        <Input {...aria} inputMode="decimal" className="min-h-11 font-mono" value={String(value)} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  )
}
