import { useState } from "react"
import { Link } from "react-router"
import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { CandidateRow } from "@/lib/candidates"
import { fmt } from "@/lib/format"
import { cn } from "@/lib/utils"

const tip = (r: CandidateRow) => (r.status === "ok" ? undefined : `${r.status}${r.error ? `: ${r.error}` : ""}`)

const num = (key: keyof CandidateRow, header: string, digits = 3): ColumnDef<CandidateRow> => ({
  accessorKey: key,
  header,
  cell: ({ getValue }) => <span className="num">{fmt(getValue() as number | null, digits)}</span>,
  sortUndefined: "last",
})

const CARD_FIELDS = [
  ["OD (mm)", "od_mm", 4],
  ["Mass (kg)", "mass_kg", 3],
  ["Torque ratio", "torque_ratio", 3],
  ["Power ratio", "power_ratio", 3],
  ["Peak power (kW)", "peak_power_kw", 3],
  ["kW/kg", "power_density", 3],
  ["Efficiency", "efficiency_base", 3],
] as const

export function CandidateTable({ rows, jobId }: { rows: CandidateRow[]; jobId: string }) {
  const [sorting, setSorting] = useState<SortingState>([])
  const href = (r: CandidateRow) => `/runs/${jobId}/candidates/${encodeURIComponent(r.id)}`
  const columns: ColumnDef<CandidateRow>[] = [
    {
      accessorKey: "id",
      header: "ID",
      cell: ({ row }) => (
        <Link to={href(row.original)} className="num text-primary underline underline-offset-2">
          {row.original.id}
        </Link>
      ),
    },
    { accessorKey: "poles", header: "Poles" },
    num("od_mm", "OD (mm)", 4),
    num("mass_kg", "Mass (kg)"),
    num("torque_ratio", "Torque ratio"),
    num("power_ratio", "Power ratio"),
    num("peak_power_kw", "Peak power (kW)"),
    num("power_density", "kW/kg"),
    num("efficiency_base", "Efficiency"),
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <span title={tip(row.original)} className={cn(row.original.status !== "ok" && "text-destructive")}>
          {row.original.status}
          {row.original.pareto && " · Pareto"}
        </span>
      ),
    },
  ]
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <>
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => {
                  const dir = h.column.getIsSorted()
                  return (
                    <TableHead key={h.id} aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"}>
                      <button
                        type="button"
                        className="inline-flex min-h-11 items-center gap-1 font-medium"
                        onClick={h.column.getToggleSortingHandler()}
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {dir === "asc" && <ArrowUp className="size-3" />}
                        {dir === "desc" && <ArrowDown className="size-3" />}
                      </button>
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((r) => (
              <TableRow key={r.id} title={tip(r.original)} className={cn(!r.original.feasible && "text-muted-foreground")}>
                {r.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="space-y-2 md:hidden">
        {table.getRowModel().rows.map((r) => {
          const c = r.original
          return (
            <li key={c.id} title={tip(c)} className="rounded-lg border border-border p-3 text-sm">
              <div className="flex items-center justify-between">
                <Link to={href(c)} className="num inline-flex min-h-11 items-center text-primary underline underline-offset-2">
                  {c.id}
                </Link>
                <span className={cn(c.status !== "ok" && "text-destructive")}>
                  {c.poles} · {c.status}
                  {c.pareto && " · Pareto"}
                </span>
              </div>
              {c.status !== "ok" && c.error && <p className="text-destructive">{c.error}</p>}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {CARD_FIELDS.map(([label, key, d]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="num">{fmt(c[key], d)}</dd>
                  </div>
                ))}
              </dl>
            </li>
          )
        })}
      </ul>
    </>
  )
}
