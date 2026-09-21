/* timer.js - drives the live countdown.
 *
 * The server is the source of truth: it renders started_at and "now" as epoch
 * milliseconds. We measure the offset between the server clock and this
 * browser's clock once, so a wrong device clock can't skew the display, and a
 * page refresh always shows the same numbers. When the bar hits 100% we ask the
 * server to close the session; the server decides what gets recorded. */
(function (root) {
  'use strict';
  var Progress = root.PT.Progress;

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return getCookie('csrftoken') || (input ? input.value : '');
  }

  function finishSession(container) {
    var url = container.dataset.stopUrl;
    if (!url) return; // someone else's progress: just show 100%

    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (response) {
      // 200 = closed now, 409 = already closed elsewhere. Either way the page is stale.
      if (response.ok || response.status === 409) {
        window.location.reload();
      } else {
        container.classList.add('is-error');
      }
    }).catch(function () {
      container.classList.add('is-error');
    });
  }

  function startStudyTimer(container) {
    var started = Number(container.dataset.started);
    var duration = Number(container.dataset.duration);
    var offset = Number(container.dataset.serverNow) - Date.now();
    var finished = false;
    var id;

    function tick() {
      var state = Progress.compute(started, duration, Date.now() + offset);
      Progress.render(container, state);
      if (state.done && !finished) {
        finished = true;
        clearInterval(id);
        finishSession(container);
      }
    }

    tick();
    id = setInterval(tick, 250);
  }

  function startBreakTimer(box) {
    var end = Number(box.dataset.end);
    var offset = Number(box.dataset.serverNow) - Date.now();
    var label = box.querySelector('[data-break-remaining]');
    var id;

    function tick() {
      var left = (end - (Date.now() + offset)) / 1000;
      if (label) label.textContent = Progress.formatClock(left);
      if (left <= 0) {
        clearInterval(id);
        box.textContent = 'Break over. Ready for the next session?';
      }
    }

    tick();
    id = setInterval(tick, 500);
  }

  root.PT.csrfToken = csrfToken;

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-timer]').forEach(startStudyTimer);
    document.querySelectorAll('[data-break-timer]').forEach(startBreakTimer);
  });
})(window);
