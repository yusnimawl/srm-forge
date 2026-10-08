import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmt } from "@/lib/format"
import type { Evaluation } from "@/lib/candidates"

export function WindingScan({ scan }: { scan: NonNullable<Evaluation["scan"]> }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Turns</TableHead>
          <TableHead>Paths</TableHead>
          <TableHead>Torque ratio</TableHead>
          <TableHead>Power ratio</TableHead>
          <TableHead>Feasible</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {scan.map((s, k) => (
          <TableRow key={k}>
            <TableCell className="num">{fmt(s.winding.turns)}</TableCell>
            <TableCell className="num">{fmt(s.winding.paths)}</TableCell>
            <TableCell className="num">{fmt(s.torque_ratio)}</TableCell>
            <TableCell className="num">{fmt(s.power_ratio)}</TableCell>
            <TableCell>{s.feasible ? "yes" : "no"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
