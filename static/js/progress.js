/* progress.js - pure helpers for progress maths and rendering.
 * No timers here; timer.js decides *when* to call these. */
(function (root) {
  'use strict';

  var pad = function (n) { return String(n).padStart(2, '0'); };

  /** 3725 -> "1:02:05", 65 -> "01:05" */
  function formatClock(totalSeconds) {
    var s = Math.max(0, Math.floor(totalSeconds));
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    return h > 0 ? h + ':' + pad(m) + ':' + pad(sec) : pad(m) + ':' + pad(sec);
  }

  /** elapsed / duration, clamped so it never goes below 0 or above 100%. */
  function compute(startedMs, durationSec, nowMs) {
    var elapsed = Math.min(Math.max((nowMs - startedMs) / 1000, 0), durationSec);
    return {
      elapsed: elapsed,
      remaining: durationSec - elapsed,
      percent: durationSec > 0 ? (elapsed / durationSec) * 100 : 100,
      done: elapsed >= durationSec
    };
  }

  /** Write a state object into the elements inside a [data-timer] container. */
  function render(container, state) {
    var fill = container.querySelector('[data-fill]');
    var percent = container.querySelector('[data-percent]');
    var elapsed = container.querySelector('[data-elapsed]');
    var remaining = container.querySelector('[data-remaining]');
    var bar = container.querySelector('[role="progressbar"]');
    if (fill) fill.style.width = state.percent.toFixed(2) + '%';
    if (percent) percent.textContent = Math.floor(state.percent);
    if (elapsed) elapsed.textContent = formatClock(state.elapsed);
    if (remaining) remaining.textContent = formatClock(state.remaining);
    if (bar) bar.setAttribute('aria-valuenow', Math.floor(state.percent));
  }

  root.PT = root.PT || {};
  root.PT.Progress = { formatClock: formatClock, compute: compute, render: render };
})(window);
