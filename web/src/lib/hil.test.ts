import { describe, expect, it } from "vitest"
import { ApiError } from "@/api/client"
import { captureSteps, hilErrorText, liveProblems, paramStatusText, ppmOff, type HilLive } from "./hil"

describe("hil", () => {
  it("names the ctrl_param statuses", () => {
    expect([0, -2, -1, -9].map(paramStatusText)).toEqual(["applied", "refused (not live)", "unknown", "refused"])
  })

  it("converts a capture length to emulator steps within the server's limits", () => {
    expect(captureSteps(10)).toBe(2000)
    expect(captureSteps(0.5)).toBe(100)
    expect(captureSteps(1000)).toBe(200000)
    expect([0.4, 1001, NaN].map(captureSteps)).toEqual([null, null, null])
  })

  it("shows the loopback text for a 403, the server text for a 409 and the field paths of a 422", () => {
    expect(hilErrorText(new ApiError(403, "the HIL rig runs only when srmweb is bound to a loopback host"))).toBe("HIL needs the server on this computer (loopback)")
    expect(hilErrorText(new ApiError(409, "start the run before capturing"))).toBe("start the run before capturing")
    expect(hilErrorText(new ApiError(422, [{ loc: ["body", "scenario", "dt"], msg: "bad" }]))).toBe("scenario.dt: bad")
  })

  it("reports the clock offset in ppm and the overruns and drops of a live window", () => {
    expect(Math.round(ppmOff(1.00002))).toBe(20)
    const ctrl = { isr_mean_us: 1, isr_max_us: 1, isr_overruns: 1, command: 0, i_meas: [], sample_us: 0, tx_dropped: 0, state: 3 }
    const live = { session: {}, emu: null, ctrl } as unknown as HilLive
    expect(liveProblems(live)).toEqual(["1 ISR overruns"])
    expect(liveProblems({ ...live, ctrl: { ...ctrl, isr_overruns: 0 } })).toEqual([])
    const dropped = { ...live, ctrl: { ...ctrl, isr_overruns: 0, tx_dropped: 5 } }
    expect(liveProblems(dropped)).toHaveLength(1)
    expect(liveProblems(dropped, 5)).toEqual([])
    expect(liveProblems(dropped, 3)).toEqual(["2 frames the controller could not send"])
  })
})
