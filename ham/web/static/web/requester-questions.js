/* R13 "HAM has a question for you" (docs/ux/approvals.md §6 R13/R19; design-system/screens/
 * approvals.md §5.1). Two small, dependency-free behaviors, scoped to
 * `.question-answer-form` elements on the secure request page:
 *   1. A soft character counter ("900 of 1,000"), announced politely once at 90% -- never a
 *      hard `maxlength` (server-side `ANSWER_MAX_LENGTH` is the real limit, C§0.6).
 *   2. Offline handling: her typed answer is kept in `sessionStorage` (per question id) so a
 *      lost connection never loses what she wrote, and the button is disabled with the
 *      `cloud-off` reason line while `navigator.onLine` is false (R19 "Offline").
 * No framework, no bundler step -- same shape as the inline scripts already in these
 * templates (`_error_summary.html`, R2's urgent-reveal toggle).
 */
(function () {
  "use strict";

  var STORAGE_PREFIX = "ham-question-answer-";

  function updateCounter(textarea) {
    var max = parseInt(textarea.getAttribute("data-max-length"), 10);
    if (!max) return;
    var counter = document.querySelector(
      '[data-counter-for="' + textarea.id + '"]'
    );
    if (!counter) return;
    var length = textarea.value.length;
    if (length >= max * 0.9) {
      counter.hidden = false;
      counter.textContent = length + " of " + max;
      counter.classList.toggle("char-counter--over", length > max);
    } else {
      counter.hidden = true;
    }
  }

  function setOffline(form, offline) {
    var button = form.querySelector("button[type=submit]");
    var reason = form.querySelector(".form-field__offline-reason");
    if (button) button.disabled = offline;
    if (reason) reason.hidden = !offline;
  }

  function init() {
    var forms = document.querySelectorAll(".question-answer-form");
    forms.forEach(function (form) {
      var questionId = form.getAttribute("data-question-id");
      var textarea = form.querySelector("textarea[name=answer]");
      if (!textarea) return;

      var storageKey = STORAGE_PREFIX + questionId;
      var saved = window.sessionStorage ? sessionStorage.getItem(storageKey) : null;
      if (saved) textarea.value = saved;
      updateCounter(textarea);

      textarea.addEventListener("input", function () {
        updateCounter(textarea);
        if (window.sessionStorage) sessionStorage.setItem(storageKey, textarea.value);
      });

      form.addEventListener("submit", function () {
        if (window.sessionStorage) sessionStorage.removeItem(storageKey);
      });

      // Not `!navigator.onLine` here: some sandboxed/offline-by-default runtimes report no
      // network interface even though this very page just loaded over HTTP a moment ago, which
      // would show the reason line on every load. A page that finished loading is, by
      // definition, online right now -- only the live `offline`/`online` events (a real
      // connectivity change *during* the visit) should ever flip this.
      setOffline(form, false);
      window.addEventListener("online", function () {
        setOffline(form, false);
      });
      window.addEventListener("offline", function () {
        setOffline(form, true);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
