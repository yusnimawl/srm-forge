import { LINE_COLORS } from "@/lib/analysis"

/** The frame after (delta 1) or before (delta -1) `index` among `count` frames, wrapping both ways. Kept to plain
 *  arithmetic so its source runs unchanged inside the report. */
export function stepFrame(index: number, count: number, delta: number): number {
  return (((index + delta) % count) + count) % count
}

/** Series colours for paper: dark counterparts of `LINE_COLORS`, same order, no blue. */
export const PRINT_LINE_COLORS = ["#222222", "#a86f00", "#3f8a2c", "#b03a80", "#c4382f", "#8a4a9a", "#666666"]

export interface AxisColors { font: string; grid: string; zero: string; line: string }
export const SCREEN_AXIS: AxisColors = { font: "#8a8a8a", grid: "#232323", zero: "#333333", line: "#232323" }
export const PRINT_AXIS: AxisColors = { font: "#333333", grid: "#dddddd", zero: "#bbbbbb", line: "#bbbbbb" }

/** The Plotly relayout update that gives a figure the axis and text colours `c`; only axes the layout has are touched.
 *  Plain code: its source runs unchanged inside the report. */
export function themeUpdate(layout: Record<string, unknown>, c: AxisColors): Record<string, string> {
  var u: Record<string, string> = { "font.color": c.font };
  ["xaxis", "yaxis", "yaxis2"].forEach(function (a) {
    if (!layout[a]) return;
    u[a + ".color"] = c.font;
    u[a + ".tickfont.color"] = c.font;
    u[a + ".gridcolor"] = c.grid;
    u[a + ".zerolinecolor"] = c.zero;
    u[a + ".linecolor"] = c.line;
  });
  return u;
}

/** The report's inline script: draws the figures and drives the flux animation. Reads the JSON blocks `figures` and
 *  `frames`; the elements it drives are created by `template.ts`. */
export const PLAYER_SOURCE = `
var stepFrame = (${stepFrame.toString()});
var themeUpdate = (${themeUpdate.toString()});
var SCREEN_LINES = ${JSON.stringify(LINE_COLORS)};
var PRINT_LINES = ${JSON.stringify(PRINT_LINE_COLORS)};
var SCREEN_AXIS = ${JSON.stringify(SCREEN_AXIS)};
var PRINT_AXIS = ${JSON.stringify(PRINT_AXIS)};
var PRINT_W_ONE = 701, PRINT_W_TWO = 341, PRINT_H = 260;
function num(x, scale, d) { return typeof x === "number" && isFinite(x) ? (x * scale).toFixed(d) : "\u2013"; }
function readJson(id) {
  var el = document.getElementById(id);
  if (!el) return null;
  try { return JSON.parse(el.textContent); } catch (err) { return null; }
}
(function () {
  var figs = readJson("figures") || [];
  figs.forEach(function (f) {
    // newPlot adopts f.layout and relayout writes into it, so the screen size is recorded first.
    f.size = { autosize: f.layout.autosize == null ? null : f.layout.autosize, width: f.layout.width == null ? null : f.layout.width, height: f.layout.height == null ? null : f.layout.height };
    try { window.Plotly.newPlot(f.id, f.data, f.layout, { displaylogo: false, responsive: true }); } catch (err) {}
  });
  // Palette index of each trace, taken before any restyle changes the colour Plotly holds in place.
  figs.forEach(function (f) {
    f.screen = f.data.map(function (t) {
      return {
        line: t.type === "scatter" && t.line ? SCREEN_LINES.indexOf(t.line.color) : -1,
        marker: (t.type === "scatter" || t.type === "bar") && t.marker && typeof t.marker.color === "string" ? SCREEN_LINES.indexOf(t.marker.color) : -1
      };
    });
  });
  function paper(on) {
    figs.forEach(function (f) {
      try {
        window.Plotly.relayout(f.id, themeUpdate(f.layout, on ? PRINT_AXIS : SCREEN_AXIS));
        // Fixed sizes: Plotly's own responsive resize is debounced and lands after the print snapshot.
        var el = document.getElementById(f.id);
        var two = el && el.closest && el.closest(".grid.two");
        window.Plotly.relayout(f.id, on
          ? { autosize: false, width: two ? PRINT_W_TWO : PRINT_W_ONE, height: PRINT_H }
          : f.size);
        f.screen.forEach(function (k, i) {
          if (k.line >= 0) window.Plotly.restyle(f.id, { "line.color": (on ? PRINT_LINES : SCREEN_LINES)[k.line] }, [i]);
          if (k.marker >= 0) window.Plotly.restyle(f.id, { "marker.color": (on ? PRINT_LINES : SCREEN_LINES)[k.marker] }, [i]);
        });
      } catch (err) {}
    });
  }
  var d = readJson("frames");
  if (!d) {
    window.addEventListener("beforeprint", function () { paper(true); });
    window.addEventListener("afterprint", function () { paper(false); });
    return;
  }
  var frames = d.frames;
  var img = document.getElementById("anim-frame");
  var play = document.getElementById("anim-play");
  var speed = document.getElementById("anim-speed");
  var scrub = document.getElementById("anim-scrub");
  var readout = document.getElementById("anim-readout");
  var values = document.getElementById("anim-values");
  var index = 0;
  var timer = null;
  function show(k) {
    index = k;
    var f = frames[k];
    img.src = f.src;
    scrub.value = String(k);
    readout.textContent = "Frame " + (k + 1) + " of " + frames.length + " at " + f.currentA.toFixed(1) + " A";
    values.textContent = "\\u03c8 " + num(f.psi, 1e3, 2) + " mWb, torque " + num(f.torque, 1, 2) + " N\\u00b7m";
  }
  function stop() {
    if (timer !== null) clearInterval(timer);
    timer = null;
    play.textContent = "Play";
  }
  function start() {
    stop();
    play.textContent = "Pause";
    timer = setInterval(function () { show(stepFrame(index, frames.length, 1)); }, 100 / Number(speed.value));
  }
  play.addEventListener("click", function () { if (timer === null) start(); else stop(); });
  speed.addEventListener("change", function () { if (timer !== null) start(); });
  scrub.addEventListener("input", function () { stop(); show(Number(scrub.value)); });
  var shownBeforePrint = 0;
  window.addEventListener("beforeprint", function () {
    shownBeforePrint = index;
    stop();
    show(0);
    paper(true);
  });
  window.addEventListener("afterprint", function () {
    show(shownBeforePrint);
    paper(false);
  });
  show(0);
})();
`
