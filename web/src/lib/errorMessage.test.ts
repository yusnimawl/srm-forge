import { describe, expect, it } from "vitest"
import { ApiError } from "@/api/client"
import { errorMessage } from "./errorMessage"

describe("errorMessage", () => {
  it("uses a string detail", () => expect(errorMessage(new ApiError(409, "job is running"))).toBe("job is running"))
  it("maps 429 to queue full", () => expect(errorMessage(new ApiError(429, "Too Many Requests"))).toMatch(/^Queue full/))
  it("falls back on status for list details", () => expect(errorMessage(new ApiError(422, []))).toBe("Request failed (422)"))
  it("handles plain errors", () => expect(errorMessage(new Error("x"))).toBe("x"))
})
