/* presence.js - "I'm still here" heartbeat and the online / studying counters.
 *
 * The server already refreshes last_seen on every page load. This adds a
 * heartbeat so someone who just stays on a page (reading, watching a timer)
 * still counts as online. It only runs while the tab is visible, which also
 * spares the database when nobody is looking. */
(function (root) {
  'use strict';
  var INTERVAL_MS = 30000;

  /** Write {online, studying} into every [data-presence] block on the page. */
  function update(counts) {
    document.querySelectorAll('[data-presence]').forEach(function (box) {
      var online = box.querySelector('[data-online]');
      var studying = box.querySelector('[data-studying]');
      if (online && counts.online !== undefined) online.textContent = counts.online;
      if (studying && counts.studying !== undefined) studying.textContent = counts.studying;
    });
  }

  function ping(url) {
    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': root.PT.csrfToken(), 'Accept': 'application/json' }
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (counts) {
      if (counts) update(counts);
    }).catch(function () { /* offline: try again next time */ });
  }

  root.PT = root.PT || {};
  root.PT.Presence = { update: update };

  document.addEventListener('DOMContentLoaded', function () {
    var url = document.body.dataset.pingUrl; // only set for logged-in users
    if (!url) return;
    setInterval(function () { if (!document.hidden) ping(url); }, INTERVAL_MS);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) ping(url); });
  });
})(window);
