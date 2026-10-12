import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import type { Material } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { parseNum } from "@/lib/searchForm"
import { Field, NumField, SELECT_CLASS, type TabProps } from "./fields"

export function MaterialTab({ form, update, errors, margin }: TabProps) {
  const materials = useQuery({ queryKey: ["materials"], queryFn: () => api<Material[]>("/api/materials") })
  const grade = (name: string) => materials.data?.find((x) => x.name === name)?.grade

  const select = (key: "stator" | "rotor", label: string) => {
    const g = grade(form[key])
    const names = materials.data?.map((x) => x.name) ?? []
    return (
      <Field id={key} label={label} error={errors[`design.machine.materials.${key}`]}>
        {(aria) => (
          <>
            <select {...aria} className={SELECT_CLASS} value={form[key]}
              onChange={(e) => update((f) => ({ ...f, [key]: e.target.value }))}>
              {!names.includes(form[key]) && <option value={form[key]}>{form[key] || "Choose a material"}</option>}
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            {g && <Badge variant="secondary" className="shrink-0">Grade {g}</Badge>}
          </>
        )}
      </Field>
    )
  }

  const explicit = parseNum(form.margin)
  const marginText = typeof explicit === "number"
    ? `Margin ${explicit} (explicit)`
    : margin != null
      ? `Margin ${margin} (from the worse of the stator and rotor grades)`
      : "Margin follows the grade once the materials are known"

  return (
    <div className="grid gap-3.5">
      {select("stator", "Stator material")}
      {select("rotor", "Rotor material")}
      <NumField id="margin" label="Margin" value={form.margin} error={errors.margin}
        hint="Empty takes the margin from the material grade."
        onChange={(v) => update((f) => ({ ...f, margin: v }))} />
      <p className="self-end pb-2 text-sm text-muted-foreground">{marginText}</p>
    </div>
  )
}
