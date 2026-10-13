// matplotlib's inferno sampled at 17 stops (data, not theme colours).
const STOPS: [number, number, number][] = [
  [0, 0, 4], [11, 7, 36], [33, 12, 74], [61, 9, 101], [87, 16, 110], [113, 25, 110], [138, 34, 106],
  [163, 44, 97], [188, 55, 84], [208, 69, 69], [227, 89, 51], [241, 113, 31], [249, 140, 10], [252, 170, 15],
  [249, 201, 50], [242, 232, 101], [252, 255, 164],
];

/** Plotly colourscale of the same stops; Plotly.js has no named "Inferno". */
export const INFERNO_SCALE: [number, string][] = STOPS.map(([r, g, b], k) => [k / (STOPS.length - 1), `rgb(${r},${g},${b})`])

export function inferno(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)) * (STOPS.length - 1);
  const i = Math.min(Math.floor(x), STOPS.length - 2);
  const f = x - i;
  return STOPS[i].map((c, k) => Math.round(c + f * (STOPS[i + 1][k] - c))) as [number, number, number];
}
