import type { components } from "./schema"

export type SearchRequest = components["schemas"]["SearchRequest"]
export type JobOut = components["schemas"]["JobOut"]

export type ValidationIssue = { loc: (string | number)[]; msg: string; type?: string }

/** `detail` is FastAPI's: a list of issues for a 422, a string otherwise. */
export class ApiError extends Error {
  status: number
  detail: ValidationIssue[] | string
  /** The parsed response body, for errors whose body is not `{detail}` (a case import's `{errors, warnings}`). */
  body: unknown
  constructor(status: number, detail: ValidationIssue[] | string, body: unknown = null) {
    super(typeof detail === "string" ? detail : `request rejected (${status})`)
    this.status = status
    this.detail = detail
    this.body = body
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" })
  if (res.status === 401 && !path.startsWith("/api/login")) {
    const here = window.location.pathname + window.location.search
    window.location.assign(`/login?next=${encodeURIComponent(here)}`)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? res.statusText, body)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const submitSearch = (payload: SearchRequest) =>
  api<{ id: string }>("/api/jobs", { method: "POST", body: JSON.stringify({ kind: "search", payload }) })
