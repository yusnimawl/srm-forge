import { describe, expect, it } from "vitest";
import { inferno } from "./inferno";

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

  it("gets lighter with t", () => {
    const lum = Array.from({ length: 9 }, (_, k) => luminance(inferno(k / 8)));
    lum.slice(1).forEach((v, k) => expect(v).toBeGreaterThan(lum[k]));
  });
});
