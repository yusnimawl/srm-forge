import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { errorMessage } from "@/lib/errorMessage"

type Coil = { name: string; phase: string; sign: "+" | "-"; d: string }
type Geometry = { view_box: [number, number, number, number]; stator: string; rotor: string; shaft: string; coils: Coil[] }

// Phase A's coils are drawn at full strength, the other phases paler.
const OTHER_PHASE_OPACITY = 0.45

function CoilShape({ coil }: { coil: Coil }) {
  return <path d={coil.d} fill="var(--coil)" fillOpacity={coil.phase === "A" ? 1 : OTHER_PHASE_OPACITY} />
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
  const [x, , w] = g.view_box
  return (
    <div className="space-y-2">
      <svg viewBox={g.view_box.join(" ")} className="mx-auto h-auto w-full max-w-[300px]" role="img" aria-label="Motor cross-section">
        <path d={g.stator} fillRule="evenodd" fill="var(--iron)" stroke="var(--iron-edge)" strokeWidth={0.2} />
        <path d={g.rotor} fillRule="evenodd" fill="var(--iron)" stroke="var(--iron-edge)" strokeWidth={0.2} />
        <path d={g.shaft} fill="var(--background)" stroke="var(--iron-edge)" strokeWidth={0.2} />
        {g.coils.map((c) => (
          <CoilShape key={c.name} coil={c} />
        ))}
        <line x1={x} x2={x + w} y1={0} y2={0} stroke="var(--primary)" strokeWidth={1} strokeDasharray="4 4" opacity={0.7}
          vectorEffect="non-scaling-stroke" />
      </svg>
      <ul className="flex flex-wrap justify-center gap-4 text-xs text-muted-foreground">
        <li className="flex items-center gap-1.5">
          <span className="inline-block size-3 rounded-sm bg-coil" />
          Phase A
        </li>
        <li className="flex items-center gap-1.5">
          <span className="inline-block size-3 rounded-sm bg-coil opacity-45" />
          Other phases
        </li>
        <li className="flex items-center gap-1.5">
          <span className="inline-block w-4 border-t border-dashed border-primary" />
          Phase A axis
        </li>
      </ul>
    </div>
  )
}
