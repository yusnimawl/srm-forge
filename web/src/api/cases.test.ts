import { describe, expect, it } from "vitest"
import { ApiError } from "./client"
import { formatIssues, requestMessage } from "./cases"

describe("formatIssues", () => {
  it("joins field: message pairs and drops the body prefix and union tags", () => {
    expect(
      formatIssues([
        { loc: ["body", "requirements", "peak_power_w"], msg: "Field required" },
        { loc: ["requirements", "wires", 0, "round", "diameter"], msg: "must be positive" },
        { loc: [], msg: "missing sections: winding" },
      ]),
    ).toBe("requirements.peak_power_w: Field required; requirements.wires.0.diameter: must be positive; missing sections: winding")
  })
})

describe("requestMessage", () => {
  it("lists a rejected request's errors and otherwise uses the API message", () => {
    const rejected = new ApiError(422, "x", { errors: [{ loc: ["margin"], msg: "too small" }], warnings: [] })
    expect(requestMessage(rejected)).toBe("margin: too small")
    expect(requestMessage(new ApiError(409, "evaluate this case first"))).toBe("evaluate this case first")
  })
})
