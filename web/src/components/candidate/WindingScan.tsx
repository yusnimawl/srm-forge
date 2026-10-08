import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmt } from "@/lib/format"
import type { Evaluation } from "@/api/types"

const head = "sticky top-0 bg-background"

/** The chosen winding's row is highlighted; the list scrolls inside a fixed height. */
export function WindingScan({ scan, chosen }: { scan: Evaluation["scan"]; chosen?: Evaluation["winding"] }) {
  const isChosen = (w: { turns: number; paths?: number | null }) =>
    chosen != null && w.turns === chosen.turns && (w.paths ?? 1) === (chosen.paths ?? 1)
  return (
    <div className="[&_[data-slot=table-container]]:max-h-80 [&_[data-slot=table-container]]:overflow-y-auto">
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className={head}>Turns</TableHead>
          <TableHead className={head}>Paths</TableHead>
          <TableHead className={head}>Torque ratio</TableHead>
          <TableHead className={head}>Power ratio</TableHead>
          <TableHead className={head}>Feasible</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {scan.map((s, k) => (
          <TableRow
            key={k}
            aria-current={isChosen(s.winding) || undefined}
            className={isChosen(s.winding) ? "bg-accent font-medium" : undefined}
          >
            <TableCell className="num">{fmt(s.winding.turns)}</TableCell>
            <TableCell className="num">{fmt(s.winding.paths)}</TableCell>
            <TableCell className="num">{fmt(s.torque_ratio)}</TableCell>
            <TableCell className="num">{fmt(s.power_ratio)}</TableCell>
            <TableCell>{s.feasible ? "yes" : "no"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    </div>
  )
}
