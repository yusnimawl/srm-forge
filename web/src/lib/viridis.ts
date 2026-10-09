// matplotlib's viridis sampled at 17 stops (data, not theme colours).
const STOPS: [number, number, number][] = [
  [68, 1, 84], [72, 24, 106], [71, 45, 123], [66, 64, 134], [59, 82, 139], [51, 99, 141], [44, 114, 142],
  [38, 130, 142], [33, 145, 140], [31, 160, 136], [40, 174, 128], [63, 188, 115], [94, 201, 98], [132, 212, 75],
  [173, 220, 48], [216, 226, 25], [253, 231, 37],
];

export function viridis(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)) * (STOPS.length - 1);
  const i = Math.min(Math.floor(x), STOPS.length - 2);
  const f = x - i;
  return STOPS[i].map((c, k) => Math.round(c + f * (STOPS[i + 1][k] - c))) as [number, number, number];
}
