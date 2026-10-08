import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { errorMessage } from "@/lib/errorMessage"

type Coil = { name: string; phase: string; sign: "+" | "-"; d: string }
type Geometry = { view_box: [number, number, number, number]; stator: string; rotor: string; shaft: string; coils: Coil[] }

// Colour-blind-safe set; the legend names the phases.
const PHASE_COLOR: Record<string, string> = { A: "#0072b2", B: "#d55e00", C: "#009e73", D: "#cc79a7" }

function CoilShape({ coil }: { coil: Coil }) {
  return (
    <path d={coil.d} fill={PHASE_COLOR[coil.phase] ?? "#888"} fillOpacity={coil.sign === "+" ? 0.9 : 0.5} stroke="var(--background)" strokeWidth={0.2} />
  )
}

export function MotorDiagram({ machine }: { machine: object }) {
  const geo = useQuery({
    queryKey: ["geometry", machine],
    queryFn: () => api<Geometry>("/api/geometry", { method: "POST", body: JSON.stringify(machine) }),
    retry: false,
  })
  if (geo.isPending) return <div className="h-64" aria-busy="true" />
  if (geo.isError) return <p className="text-sm text-destructive">Cross-section unavailable: {errorMessage(geo.error)}</p>
  const g = geo.data
  const phases = [...new Set(g.coils.map((c) => c.phase))].sort()
  return (
    <div className="space-y-2">
      <svg viewBox={g.view_box.join(" ")} className="mx-auto h-auto w-full max-w-md" role="img" aria-label="Motor cross-section">
        <path d={g.stator} fillRule="evenodd" fill="var(--muted)" stroke="var(--muted-foreground)" strokeWidth={0.2} />
        <path d={g.rotor} fillRule="evenodd" fill="var(--muted)" stroke="var(--muted-foreground)" strokeWidth={0.2} />
        <path d={g.shaft} fill="var(--background)" stroke="var(--muted-foreground)" strokeWidth={0.2} />
        {g.coils.map((c) => (
          <CoilShape key={c.name} coil={c} />
        ))}
      </svg>
      <ul className="flex flex-wrap justify-center gap-4 text-sm">
        {phases.map((p) => (
          <li key={p} className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm" style={{ background: PHASE_COLOR[p] ?? "#888" }} />
            Phase {p}
          </li>
        ))}
        <li className="text-muted-foreground">+ / - : coil side direction (paler = -)</li>
      </ul>
    </div>
  )
}
