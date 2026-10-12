import { useRef, useState, type ReactNode } from "react"
import { Link } from "react-router"
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table"
import { MessageSquare, Tag, Trash2 } from "lucide-react"
import type { CasePatch } from "@/api/cases"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { MAX_SHOWN, type CaseRow, type CaseStatus } from "@/lib/cases"
import { fmt } from "@/lib/format"
import { cn } from "@/lib/utils"

export type CaseActions = {
  patch: (id: string, patch: CasePatch) => void
  remove: (row: CaseRow) => void
  /** False once `MAX_SHOWN` cases are shown in the graphs. */
  canShowMore: boolean
}

const STATUS_CLASS: Record<CaseStatus, string> = {
  Draft: "bg-secondary text-secondary-foreground",
  Evaluated: "",
  "2D-verified": "bg-feasible/15 text-feasible",
  Failed: "bg-destructive/15 text-destructive",
}

export const CaseStatusBadge = ({ status }: { status: CaseStatus }) => (
  <Badge variant="outline" className={STATUS_CLASS[status]}>
    {status}
  </Badge>
)

/** Text that turns into an input on click; Enter or leaving the field commits, Escape cancels. An empty value is committed only when `allowEmpty`. */
function InlineText({
  value,
  onCommit,
  maxLength,
  label,
  allowEmpty = false,
  children,
}: {
  value: string
  onCommit: (v: string) => void
  maxLength: number
  label: string
  allowEmpty?: boolean
  children: ReactNode
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const done = useRef(false)
  const finish = (save: boolean) => {
    if (done.current) return
    done.current = true
    setEditing(false)
    const v = draft.trim()
    if (save && v !== value && (v !== "" || allowEmpty)) onCommit(v)
  }
  if (!editing)
    return (
      <button
        type="button"
        aria-label={`Edit ${label}`}
        className="min-h-11 max-w-full rounded-md px-1 text-left hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => {
          done.current = false
          setDraft(value)
          setEditing(true)
        }}
      >
        {children}
      </button>
    )
  return (
    <Input
      autoFocus
      aria-label={label}
      className="h-11 min-w-32"
      maxLength={maxLength}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => finish(true)}
      onKeyDown={(e) => {
        if (e.key === "Enter") finish(true)
        if (e.key === "Escape") finish(false)
      }}
    />
  )
}

const FlagCell = ({ row, a }: { row: CaseRow; a: CaseActions }) => (
  <InlineText value={row.flag ?? ""} label="flag" maxLength={40} allowEmpty onCommit={(v) => a.patch(row.id, { flag: v })}>
    {row.flag ? (
      <Badge variant="secondary" className="max-w-40">
        <span className="truncate">{row.flag}</span>
      </Badge>
    ) : (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Tag className="size-3" /> Flag
      </span>
    )}
  </InlineText>
)

const LabelCell = ({ row, a }: { row: CaseRow; a: CaseActions }) => (
  <div className="flex min-w-0 items-center gap-1">
    <InlineText value={row.label} label="label" maxLength={120} onCommit={(v) => a.patch(row.id, { label: v })}>
      <span className="block truncate font-medium">{row.label}</span>
    </InlineText>
    <Button variant="link" className="min-h-11 shrink-0 px-1" render={<Link to={`/cases/${row.id}`} />}>
      Open
    </Button>
  </div>
)

function CommentCell({ row, a }: { row: CaseRow; a: CaseActions }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState("")
  const has = !!row.comment
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        if (o) setDraft(row.comment ?? "")
        setOpen(o)
      }}
    >
      <PopoverTrigger
        render={<Button variant="ghost" size="icon" className="size-11" aria-label={has ? `Comment: ${row.comment}` : "Add comment"} title={row.comment ?? undefined} />}
      >
        <MessageSquare className={cn("size-4", has ? "fill-primary/20 text-primary" : "text-muted-foreground")} />
      </PopoverTrigger>
      <PopoverContent className="space-y-2">
        <textarea
          aria-label="Comment"
          className="min-h-24 w-full rounded-lg border border-input bg-transparent p-2 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm"
          maxLength={2000}
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="min-h-11" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            className="min-h-11"
            onClick={() => {
              if (draft !== (row.comment ?? "")) a.patch(row.id, { comment: draft })
              setOpen(false)
            }}
          >
            Save
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function ShowCell({ row, a }: { row: CaseRow; a: CaseActions }) {
  const blocked = !row.show_in_graphs && !a.canShowMore
  const box = (
    <input
      type="checkbox"
      className="size-5 accent-primary"
      aria-label={`Show ${row.label} in graphs`}
      checked={row.show_in_graphs}
      disabled={blocked}
      onChange={(e) => a.patch(row.id, { show_in_graphs: e.target.checked })}
    />
  )
  return blocked ? (
    <Tooltip>
      <TooltipTrigger render={<span className="inline-flex size-11 items-center justify-center" />}>{box}</TooltipTrigger>
      <TooltipContent>At most {MAX_SHOWN} cases</TooltipContent>
    </Tooltip>
  ) : (
    <label className="inline-flex size-11 items-center justify-center">{box}</label>
  )
}

const DeleteCell = ({ row, a }: { row: CaseRow; a: CaseActions }) => (
  <Button variant="ghost" size="icon" className="size-11 text-destructive" aria-label={`Delete ${row.label}`} onClick={() => a.remove(row)}>
    <Trash2 className="size-4" />
  </Button>
)

type NumKey = "torque_ratio" | "power_ratio" | "peak_power_kw" | "mass_kg" | "power_density" | "efficiency_base"

const num = (key: NumKey, header: string): ColumnDef<CaseRow> => ({
  accessorKey: key,
  header,
  cell: ({ getValue }) => <span className="num">{fmt(getValue() as number | null)}</span>,
})

const columns = (a: CaseActions): ColumnDef<CaseRow>[] => [
  { id: "flag", header: "Flag", cell: ({ row }) => <FlagCell row={row.original} a={a} /> },
  { id: "label", header: "Label", cell: ({ row }) => <LabelCell row={row.original} a={a} /> },
  { accessorKey: "origin", header: "Origin" },
  { accessorKey: "poles", header: "Poles", cell: ({ getValue }) => (getValue() as string | null) ?? "—" },
  { accessorKey: "preset", header: "Preset", cell: ({ getValue }) => (getValue() as string | null) ?? "—" },
  { id: "status", header: "Status", cell: ({ row }) => <CaseStatusBadge status={row.original.status} /> },
  num("torque_ratio", "Torque ratio"),
  num("power_ratio", "Power ratio"),
  num("peak_power_kw", "Peak power (kW)"),
  num("mass_kg", "Mass (kg)"),
  num("power_density", "kW/kg"),
  num("efficiency_base", "Efficiency"),
  { id: "comment", header: "Comment", cell: ({ row }) => <CommentCell row={row.original} a={a} /> },
  { id: "show", header: "Show in graphs", cell: ({ row }) => <ShowCell row={row.original} a={a} /> },
  { id: "delete", header: () => <span className="sr-only">Delete</span>, cell: ({ row }) => <DeleteCell row={row.original} a={a} /> },
]

const CARD_FIELDS: [string, NumKey][] = [
  ["Torque ratio", "torque_ratio"],
  ["Power ratio", "power_ratio"],
  ["Peak power (kW)", "peak_power_kw"],
  ["Mass (kg)", "mass_kg"],
  ["kW/kg", "power_density"],
  ["Efficiency", "efficiency_base"],
]

function CaseCard({ row, a }: { row: CaseRow; a: CaseActions }) {
  return (
    <li className="space-y-2 rounded-lg border border-border p-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <FlagCell row={row} a={a} />
        <CaseStatusBadge status={row.status} />
      </div>
      <LabelCell row={row} a={a} />
      <div className="text-muted-foreground">
        {row.origin} · {row.poles ?? "—"} · {row.preset ?? "—"}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
        {CARD_FIELDS.map(([name, key]) => (
          <div key={key} className="flex justify-between gap-2">
            <dt className="text-muted-foreground">{name}</dt>
            <dd className="num">{fmt(row[key])}</dd>
          </div>
        ))}
      </dl>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1">
          <ShowCell row={row} a={a} /> Show in graphs
        </span>
        <span className="flex">
          <CommentCell row={row} a={a} />
          <DeleteCell row={row} a={a} />
        </span>
      </div>
    </li>
  )
}

export function CaseTable({ rows, actions }: { rows: CaseRow[]; actions: CaseActions }) {
  const table = useReactTable({ data: rows, columns: columns(actions), getCoreRowModel: getCoreRowModel(), getRowId: (r) => r.id })
  return (
    <>
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((g) => (
              <TableRow key={g.id}>
                {g.headers.map((h) => (
                  <TableHead key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((r) => (
              <TableRow key={r.id}>
                {r.getVisibleCells().map((c) => (
                  <TableCell key={c.id}>{flexRender(c.column.columnDef.cell, c.getContext())}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="space-y-2 md:hidden">
        {rows.map((r) => (
          <CaseCard key={r.id} row={r} a={actions} />
        ))}
      </ul>
    </>
  )
}
