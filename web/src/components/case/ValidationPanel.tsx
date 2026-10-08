import type { Validation, Winding } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmt, fmtSI } from "@/lib/format"
import { fromSI, UNIT_LABEL, type Unit } from "@/lib/units"
import { atScale, turnsScale } from "@/lib/validation"
import { cn } from "@/lib/utils"

const KEY_LABEL: Record<string, { label: string; unit?: Unit }> = {
  la: { label: "La", unit: "mH" },
  lu: { label: "Lu", unit: "mH" },
  peak_torque: { label: "Peak torque", unit: "Nm" },
  psi_max: { label: "ψ max", unit: "mWb" },
}

const STATUS_CLASS: Record<string, string> = {
  pass: "bg-feasible/15 text-feasible",
  warn: "bg-secondary text-secondary-foreground",
  fail: "bg-destructive/15 text-destructive",
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `${fmt(fromSI(v, "%"), 2)} %`)

/** The EM-validation result: label, every check with its value and limit, and the uncertainty budget. The absolute key
 *  numbers belong to the reference winding the map was built at; with the case's `winding` they are shown rescaled to it
 *  (the relative rows are unchanged by turns). */
export function ValidationPanel({ validation, winding }: { validation: Validation; winding?: Pick<Winding, "turns" | "paths"> | null }) {
  const { budget } = validation
  const k = winding ? turnsScale(winding, validation.reference_turns) : 1
  const values2d = atScale(budget.values_2d, k)
  const values = atScale(budget.values, k)
  const basis = winding
    ? `Key numbers at the case's winding (${winding.turns} turns per pole${winding.paths > 1 ? `, ${winding.paths} paths` : ""}).`
    : `Key numbers at the ${validation.reference_turns}-turn reference winding.`
  const keys = Object.keys(budget.values)
  const head = (k: string) => `${KEY_LABEL[k]?.label ?? k}${KEY_LABEL[k]?.unit ? ` (${UNIT_LABEL[KEY_LABEL[k].unit!]})` : ""}`
  const val = (k: string, v: number | null | undefined) => (KEY_LABEL[k]?.unit ? fmtSI(v, KEY_LABEL[k].unit!, 4) : fmt(v, 4))
  return (
    <section aria-label="EM validation" className="min-w-0 space-y-4">
      <h2 className="text-lg font-semibold">
        EM validation: {validation.label ?? "not validated"}
        <span className="ml-2 text-sm font-normal text-muted-foreground">srmcore {validation.engine_version}</span>
      </h2>
      {Object.keys(validation.material_grades).length > 0 && (
        <p className="text-sm text-muted-foreground">
          B-H grades: {Object.entries(validation.material_grades).map(([m, g]) => `${m} ${g}`).join(", ")}
        </p>
      )}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Check</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead className="text-right">Limit</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {validation.checks.map((c) => (
              <TableRow key={c.name}>
                <TableCell className="num">{c.name}</TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn("uppercase", STATUS_CLASS[c.status])}>{c.status}</Badge>
                </TableCell>
                <TableCell className="num text-right">{fmt(c.value, 3)}</TableCell>
                <TableCell className="num text-right">{fmt(c.limit, 3)}</TableCell>
                <TableCell className="whitespace-normal text-muted-foreground">{c.detail}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Uncertainty budget</h3>
        <p className="text-xs text-muted-foreground">
          {basis} Worst-case relative error of each key number, against the end-winding-corrected value.
        </p>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                {keys.map((k) => <TableHead key={k} className="text-right">{head(k)}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>2D map value</TableCell>
                {keys.map((k) => <TableCell key={k} className="num text-right">{val(k, values2d[k])}</TableCell>)}
              </TableRow>
              <TableRow>
                <TableCell>With end winding</TableCell>
                {keys.map((k) => <TableCell key={k} className="num text-right">{val(k, values[k])}</TableCell>)}
              </TableRow>
              {budget.rows.map((r) => (
                <TableRow key={r.source}>
                  <TableCell className="whitespace-normal">
                    {r.source}
                    <span className="block text-xs text-muted-foreground">{r.note}</span>
                  </TableCell>
                  {keys.map((k) => <TableCell key={k} className="num text-right">{pct(r.rel[k])}</TableCell>)}
                </TableRow>
              ))}
              <TableRow className="font-medium">
                <TableCell>Total</TableCell>
                {keys.map((k) => <TableCell key={k} className="num text-right">{pct(budget.total[k])}</TableCell>)}
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </div>
    </section>
  )
}
