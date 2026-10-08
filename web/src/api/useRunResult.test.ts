import { describe, expect, it } from "vitest"
import { ApiError } from "@/api/client"
import { resultOrNull } from "./useRunResult"

describe("resultOrNull", () => {
  it("passes a value through", async () => expect(await resultOrNull(async () => 5)).toBe(5))
  it("maps 404 to null", async () => {
    expect(await resultOrNull(async () => { throw new ApiError(404, "no result") })).toBeNull()
  })
  it("rethrows other errors", async () => {
    await expect(resultOrNull(async () => { throw new ApiError(500, "boom") })).rejects.toThrow()
  })
})
