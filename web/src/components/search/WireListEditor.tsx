import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { newWire, type WireForm } from "@/lib/searchForm"
import { UNIT_LABEL } from "@/lib/units"

const FIELDS: Record<WireForm["kind"], { key: string; label: string; mm?: boolean }[]> = {
  round: [{ key: "diameter", label: "Bare diameter", mm: true }, { key: "outer_diameter", label: "Outer diameter", mm: true }],
  rectangular: [
    { key: "width", label: "Width", mm: true }, { key: "height", label: "Height", mm: true },
    { key: "insulation", label: "Insulation per side", mm: true },
  ],
  litz: [
    { key: "strand_diameter", label: "Strand diameter", mm: true }, { key: "strands", label: "Strands" },
    { key: "outer_diameter", label: "Bundle outer diameter", mm: true },
  ],
}
const KIND_LABEL: Record<WireForm["kind"], string> = { round: "Round", rectangular: "Rectangular", litz: "Litz" }

type Props = {
  wires: WireForm[]
  onChange: (wires: WireForm[]) => void
  errors: Record<string, string>
}

export function WireListEditor({ wires, onChange, errors }: Props) {
  const set = (i: number, key: string, value: string) =>
    onChange(wires.map((w, j) => (j === i ? ({ ...w, [key]: value } as WireForm) : w)))

  return (
    <div className="space-y-3">
      {wires.length === 0 && (
        <p className="text-sm text-muted-foreground">No wires yet. Add at least one to search in wire mode.</p>
      )}
      {wires.map((w, i) => (
        <fieldset key={i} className="rounded-[10px] border border-border bg-card p-3">
          <legend className="px-1 text-[13px] font-medium text-muted-foreground">{KIND_LABEL[w.kind]} wire {i + 1}</legend>
          {errors[`requirements.wires.${i}`] && (
            <p role="alert" className="mb-2 text-sm text-destructive">{errors[`requirements.wires.${i}`]}</p>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            {FIELDS[w.kind].map((f) => {
              const id = `wire-${i}-${f.key}`
              const err = errors[`requirements.wires.${i}.${f.key}`]
              return (
                <div key={f.key} className="space-y-1.5">
                  <Label htmlFor={id} className="text-[13px] font-normal leading-snug text-muted-foreground">{f.label}{f.mm ? ` (${UNIT_LABEL.mm})` : ""}</Label>
                  <Input id={id} inputMode="decimal" className="min-h-11 font-mono" aria-invalid={!!err}
                    aria-describedby={err ? `${id}-err` : undefined}
                    value={String((w as Record<string, unknown>)[f.key])}
                    onChange={(e) => set(i, f.key, e.target.value)} />
                  {err && <p id={`${id}-err`} className="text-sm text-destructive">{err}</p>}
                </div>
              )
            })}
          </div>
          <Button type="button" variant="ghost" className="mt-2 min-h-11"
            onClick={() => onChange(wires.filter((_, j) => j !== i))}>
            <Trash2 aria-hidden /> Remove wire {i + 1}
          </Button>
        </fieldset>
      ))}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(KIND_LABEL) as WireForm["kind"][]).map((k) => (
          <Button key={k} type="button" variant="outline" className="min-h-11" onClick={() => onChange([...wires, newWire(k)])}>
            <Plus aria-hidden /> {KIND_LABEL[k]}
          </Button>
        ))}
      </div>
    </div>
  )
}
