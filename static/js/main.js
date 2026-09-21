/* main.js - small UI behaviours: mobile nav, expandable cards, start picker. */
document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  // Mobile navigation
  var toggle = document.querySelector('[data-nav-toggle]');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }

  // Expand / collapse task descriptions (works on touch: not hover-only)
  document.querySelectorAll('[data-toggle-more]').forEach(function (button) {
    button.addEventListener('click', function () {
      var panel = document.getElementById(button.dataset.toggleMore);
      if (!panel) return;
      var open = panel.classList.toggle('is-open');
      button.setAttribute('aria-expanded', String(open));
      var label = button.querySelector('[data-more-label]');
      if (label) label.textContent = open ? 'Hide' : 'Details';
    });
  });

  // Dashboard: the START button posts to whichever task is selected
  var select = document.querySelector('[data-start-select]');
  var form = document.querySelector('[data-start-form]');
  if (select && form) {
    var sync = function () { form.action = select.value; };
    select.addEventListener('change', sync);
    sync();
  }

  // Confirm destructive actions
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (event) {
      if (!window.confirm(f.dataset.confirm)) event.preventDefault();
    });
  });

  // Dismissable messages
  document.querySelectorAll('[data-dismiss]').forEach(function (button) {
    button.addEventListener('click', function () { button.parentElement.remove(); });
  });
});
