import { ApiError } from "@/api/client"

/** A readable message for a failed request: the API's string detail, else a status-based fallback. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string" && e.detail && e.status !== 429) return e.detail
    if (e.status === 429) return "Queue full — wait for a run to finish"
    if (e.status === 409) return "The run changed state; refresh and try again"
    if (e.status === 404) return "Run not found"
    return `Request failed (${e.status})`
  }
  return e instanceof Error ? e.message : "Request failed"
}
