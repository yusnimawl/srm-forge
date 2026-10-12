import type { ReactNode } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { CaseForm } from "@/lib/caseForm"
import { UNIT_LABEL, type Unit } from "@/lib/units"

export const SELECT_CLASS =
  "min-h-11 w-full rounded-[6px] border border-border-strong bg-background px-2.5 font-mono text-[13px] outline-none focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-primary/[0.08] aria-invalid:border-destructive disabled:opacity-50"

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
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,9rem)] items-center gap-x-3 gap-y-1.5">
      <Label htmlFor={id} className="text-[13px] font-normal leading-snug text-muted-foreground">{label}</Label>
      <div className="relative [&_input]:pr-14">
        {children({ id, "aria-invalid": !!error, "aria-describedby": described })}
        {unitText && <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-faint">{unitText}</span>}
      </div>
      {hint && <p id={`${id}-hint`} className="col-span-2 text-xs text-faint">{hint}</p>}
      {error && <p id={`${id}-err`} className="col-span-2 text-right text-xs text-destructive">{error}</p>}
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
        <Input {...aria} inputMode="decimal" className="min-h-11" value={String(value)} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  )
}
