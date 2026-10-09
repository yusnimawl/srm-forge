import { useMutation, useQuery } from "@tanstack/react-query"
import { ApiError } from "./client"
import { frameFromWire, meshFromWire } from "@/lib/fieldWire"

/** Binary response; errors are `ApiError`s with the JSON `detail`, like `api`'s. */
async function binary(path: string, init: RequestInit = {}): Promise<ArrayBuffer> {
  const res = await fetch(path, { ...init, credentials: "same-origin" })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? res.statusText, body)
  }
  return res.arrayBuffer()
}

export const useFieldMesh = (caseId: string, enabled = true) =>
  useQuery({
    queryKey: ["field-mesh", caseId],
    queryFn: async () => meshFromWire(await binary(`/api/cases/${caseId}/field/mesh`)),
    staleTime: Infinity,
    enabled,
  })

/** One field frame at a mechanical angle (rad, [0, 2 pi)) and phase current (A). */
export const useFieldSnapshot = (caseId: string) =>
  useMutation({
    mutationFn: async (v: { angle: number; current_a: number }) =>
      frameFromWire(
        await binary(`/api/cases/${caseId}/field`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(v),
        }),
      ),
  })
