/** The frame after (delta 1) or before (delta -1) `index` among `count` frames, wrapping both ways. Kept to plain
 *  arithmetic so its source runs unchanged inside the report. */
export function stepFrame(index: number, count: number, delta: number): number {
  return (((index + delta) % count) + count) % count
}

/** The report's inline script: draws the figures and drives the flux animation. Reads the JSON blocks `figures` and
 *  `frames`; the elements it drives are created by `template.ts`. */
export const PLAYER_SOURCE = `
var stepFrame = (${stepFrame.toString()});
(function () {
  var figs = JSON.parse(document.getElementById("figures").textContent);
  figs.forEach(function (f) {
    window.Plotly.newPlot(f.id, f.data, f.layout, { displaylogo: false, responsive: true });
  });
  var meta = document.getElementById("frames");
  if (!meta) return;
  var d = JSON.parse(meta.textContent);
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
    values.textContent = "\\u03c8 " + (f.psi * 1e3).toFixed(2) + " mWb, torque " + f.torque.toFixed(2) + " N\\u00b7m";
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
  show(0);
})();
`
