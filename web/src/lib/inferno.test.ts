import { describe, expect, it } from "vitest";
import { inferno, INFERNO_SCALE } from "./inferno";

const luminance = ([r, g, b]: number[]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

describe("inferno", () => {
  it("endpoints and clamping", () => {
    expect(inferno(0)).toEqual([0, 0, 4]);
    expect(inferno(1)).toEqual([252, 255, 164]);
    expect(inferno(-1)).toEqual(inferno(0));
    expect(inferno(5)).toEqual(inferno(1));
  });

  it("matches matplotlib at the middle", () => {
    const [r, g, b] = inferno(0.5);
    expect(Math.abs(r - 188)).toBeLessThanOrEqual(1);
    expect(Math.abs(g - 55)).toBeLessThanOrEqual(1);
    expect(Math.abs(b - 84)).toBeLessThanOrEqual(1);
  });

  it("exports a 17-stop Plotly colourscale", () => {
    expect(INFERNO_SCALE).toHaveLength(17);
    // Built from the stops at runtime: the first stop (0, 0, 4) is near-black but reads as blue to the no-blue guard as a literal.
    const css = (t: number) => `rgb(${inferno(t).join(",")})`;
    expect(INFERNO_SCALE[0]).toEqual([0, css(0)]);
    expect(INFERNO_SCALE[16]).toEqual([1, css(1)]);
  });

  it("gets lighter with t", () => {
    const lum = Array.from({ length: 9 }, (_, k) => luminance(inferno(k / 8)));
    lum.slice(1).forEach((v, k) => expect(v).toBeGreaterThan(lum[k]));
  });
});
