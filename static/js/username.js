/* username.js - the required "choose your username" pop-up.
 *
 * The rest of the page is made inert (no clicks, no keyboard focus) while the
 * pop-up is open and Escape does nothing, because choosing a name is required.
 * The form is sent with fetch; the server answers JSON so errors show inline. */
document.addEventListener('DOMContentLoaded', function () {
  'use strict';
  var modal = document.getElementById('username-modal');
  if (!modal) return;

  var form = modal.querySelector('[data-username-form]');
  var errorBox = modal.querySelector('[data-username-errors]');
  var input = form.querySelector('input[name="username"]');
  var submit = form.querySelector('button[type="submit"]');

  document.body.classList.add('modal-open');
  document.querySelectorAll('.topbar, #main').forEach(function (el) { el.inert = true; });
  input.focus();

  // Keep Tab inside the pop-up.
  modal.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var focusable = Array.prototype.slice.call(modal.querySelectorAll('input:not([type="hidden"]), button:not([disabled])'));
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    errorBox.textContent = '';
    submit.disabled = true;

    fetch(form.action, {
      method: 'POST',
      body: new FormData(form), // includes the CSRF token field
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
    }).then(function (response) {
      return response.json().then(function (data) { return { ok: response.ok && data.ok, data: data }; });
    }).then(function (result) {
      if (result.ok) {
        window.location.reload(); // the pop-up is gone once the server no longer asks for a name
        return;
      }
      var errors = (result.data.errors && result.data.errors.username) || ['Something went wrong. Try again.'];
      errorBox.textContent = errors.join(' ');
      input.setAttribute('aria-invalid', 'true');
      input.focus();
      submit.disabled = false;
    }).catch(function () {
      errorBox.textContent = 'Could not reach the server. Check your connection and try again.';
      submit.disabled = false;
    });
  });
});
