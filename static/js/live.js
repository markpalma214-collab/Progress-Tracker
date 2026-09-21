/* live.js - the live study room.
 *
 * Two loops with different jobs:
 *   1. Poll /live/data/ every few seconds: WHO is studying (add / remove cards).
 *   2. A 250 ms ticker: HOW FAR along each bar is, computed locally from the
 *      server's start time (same maths as the dashboard), so bars glide
 *      smoothly without a request per second.
 * User-supplied text is only ever written with textContent (never innerHTML). */
(function (root) {
  'use strict';
  var Progress = root.PT.Progress;

  document.addEventListener('DOMContentLoaded', function () {
    var list = document.getElementById('live-list');
    if (!list) return;
    var emptyNote = document.querySelector('[data-live-empty]');
    var statusNote = document.querySelector('[data-live-status]');
    var url = list.dataset.liveUrl;
    var interval = Number(list.dataset.pollMs) || 5000;

    var cards = {};      // username -> { el, charge, started, duration }
    var offset = 0;      // server clock minus browser clock
    var timeoutId = null;
    var busy = false;

    function make(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function buildCard(s) {
      var el = make('article', 'card live-card');

      var head = make('header', 'task-head');
      var name = make('h3', 'task-title');
      var link = make('a', '', s.username);
      link.href = s.url;
      name.appendChild(link);
      head.appendChild(name);
      if (s.is_me) head.appendChild(make('span', 'badge badge-running', 'You'));
      el.appendChild(head);
      el.appendChild(make('p', 'live-title muted', s.title));

      var charge = make('div', 'charge');
      charge.setAttribute('data-live', '');
      var top = make('div', 'charge-head');
      var pct = make('span', 'charge-percent');
      pct.appendChild(make('span', '', '0')).setAttribute('data-percent', '');
      pct.appendChild(document.createTextNode('%'));
      var left = make('span', 'charge-left');
      left.appendChild(make('span', '', '00:00')).setAttribute('data-remaining', '');
      left.appendChild(document.createTextNode(' '));
      left.appendChild(make('small', '', 'remaining'));
      top.appendChild(pct);
      top.appendChild(left);

      var bar = make('div', 'charge-bar');
      bar.setAttribute('role', 'progressbar');
      bar.setAttribute('aria-label', 'Progress for ' + s.username);
      bar.setAttribute('aria-valuemin', '0');
      bar.setAttribute('aria-valuemax', '100');
      bar.setAttribute('aria-valuenow', '0');
      var fill = make('div', 'charge-fill');
      fill.setAttribute('data-fill', '');
      bar.appendChild(fill);

      var foot = make('div', 'charge-foot');
      var elapsed = make('span', '', 'Elapsed ');
      elapsed.appendChild(make('b', '', '00:00')).setAttribute('data-elapsed', '');
      foot.appendChild(elapsed);
      foot.appendChild(make('span', '', 'Planned ' + Math.round(s.duration / 60) + ' min'));

      charge.appendChild(top);
      charge.appendChild(bar);
      charge.appendChild(foot);
      el.appendChild(charge);
      return { el: el, charge: charge, started: s.started, duration: s.duration, title: s.title };
    }

    function reconcile(sessions) {
      var seen = {};
      sessions.forEach(function (s) {
        seen[s.username] = true;
        var existing = cards[s.username];
        if (existing && (existing.started !== s.started || existing.title !== s.title)) {
          existing.el.remove();   // same user, new session: rebuild
          existing = null;
        }
        if (!existing) cards[s.username] = existing = buildCard(s);
        list.appendChild(existing.el); // appending an existing node also keeps server order
      });
      Object.keys(cards).forEach(function (username) {
        if (!seen[username]) {
          cards[username].el.remove();
          delete cards[username];
        }
      });
      emptyNote.hidden = sessions.length > 0;
      emptyNote.textContent = 'Nobody is studying right now.';
    }

    function tick() {
      var now = Date.now() + offset;
      Object.keys(cards).forEach(function (username) {
        var c = cards[username];
        Progress.render(c.charge, Progress.compute(c.started, c.duration, now));
      });
    }

    function schedule() {
      clearTimeout(timeoutId);
      if (!document.hidden) timeoutId = setTimeout(poll, interval);
    }

    function poll() {
      if (busy) return;
      busy = true;
      fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (response) {
          if (response.status === 401) { window.location.reload(); return null; }
          if (!response.ok) throw new Error('bad status ' + response.status);
          return response.json();
        })
        .then(function (data) {
          if (!data) return;
          offset = data.now - Date.now();
          reconcile(data.sessions);
          tick();
          if (root.PT.Presence) root.PT.Presence.update(data);
          statusNote.textContent = '';
        })
        .catch(function () {
          statusNote.textContent = 'Connection lost. Retrying…';
        })
        .then(function () { busy = false; schedule(); });
    }

    setInterval(tick, 250);
    // Stop polling while the tab is hidden; catch up the moment it is shown again.
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) clearTimeout(timeoutId); else poll();
    });
    poll();
  });
})(window);
