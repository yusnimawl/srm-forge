import { describe, expect, it } from "vitest"
import { ApiError } from "@/api/client"
import { CAPTURE_RING, captureSteps, DEFAULT_CAPTURE_MS, hilErrorText, liveProblems, liveWarnings, paramStatusText, ppmOff, type HilLive } from "./hil"

describe("hil", () => {
  it("names the ctrl_param statuses", () => {
    expect([0, -2, -1, -9].map(paramStatusText)).toEqual(["applied", "refused (not live)", "unknown", "refused"])
  })

  it("converts a capture length to emulator steps within the server's limits", () => {
    expect(captureSteps(12)).toBe(2000)
    expect(captureSteps(0.6)).toBe(100)
    expect(captureSteps(1200)).toBe(200000)
    expect([0.5, 1201, NaN].map(captureSteps)).toEqual([null, null, null])
    expect(captureSteps(DEFAULT_CAPTURE_MS)).toBe(CAPTURE_RING)          // the default capture fills the buffered ring
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

  it("warns, without a problem, when the emulator step max is above 80 % of the step", () => {
    const emu = { step_max_us: 4.8, overruns: 0, dropped: 0 }
    const live = { session: {}, emu, ctrl: null } as unknown as HilLive
    expect(liveWarnings(live)).toEqual([])
    const slow = { ...live, emu: { ...emu, step_max_us: 5.04 } } as unknown as HilLive
    expect(liveWarnings(slow)).toEqual(["emulator step max 5.04 µs is 84 % of the 6 µs step (warning above 80 %)"])
    expect(liveProblems(slow)).toEqual([])
    expect(liveWarnings({ ...live, emu: null })).toEqual([])
  })
})
