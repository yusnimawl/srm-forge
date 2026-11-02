import { Badge } from "@/components/ui/badge"
import type { CaseStatus } from "@/lib/cases"

const STATUS_VARIANT: Record<CaseStatus, "secondary" | "outline" | "ok" | "destructive"> = {
  Draft: "secondary",
  Evaluated: "outline",
  "2D-verified": "ok",
  Failed: "destructive",
}

export const CaseStatusBadge = ({ status }: { status: CaseStatus }) => (
  <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>
)
