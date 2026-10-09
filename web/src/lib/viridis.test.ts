import { describe, expect, it } from "vitest";
import { viridis } from "./viridis";

describe("viridis", () => {
  it("endpoints and clamping", () => {
    expect(viridis(0)).toEqual([68, 1, 84]);
    expect(viridis(1)).toEqual([253, 231, 37]);
    expect(viridis(-1)).toEqual(viridis(0));
    expect(viridis(5)).toEqual(viridis(1));
  });

  it("matches matplotlib at the middle", () => {
    const [r, g, b] = viridis(0.5);
    expect(Math.abs(r - 33)).toBeLessThanOrEqual(1);
    expect(Math.abs(g - 145)).toBeLessThanOrEqual(1);
    expect(Math.abs(b - 140)).toBeLessThanOrEqual(1);
  });
});
