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
 *
 * Fix 3E / security L7, UX M8: a draft is cleared ONLY once the server has actually
 * confirmed the answer was recorded (`?answered=<id>` on the redirect back to this page) --
 * clearing on every `submit` event (the old behavior) lost her typed text on a validation
 * failure or a dropped connection, exactly the case this module exists to protect against.
 * `?answer_failed=<id>` (either reason) leaves the draft alone. Drafts for a question that
 * isn't open anymore (withdrawn, answered from another tab, or just old) are pruned on load.
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

  function pruneClosedDrafts(openQuestionIds) {
    if (!window.sessionStorage) return;
    var toRemove = [];
    for (var i = 0; i < sessionStorage.length; i++) {
      var key = sessionStorage.key(i);
      if (key && key.indexOf(STORAGE_PREFIX) === 0) {
        var questionId = key.slice(STORAGE_PREFIX.length);
        if (openQuestionIds.indexOf(questionId) === -1) toRemove.push(key);
      }
    }
    toRemove.forEach(function (key) {
      sessionStorage.removeItem(key);
    });
  }

  function init() {
    var forms = document.querySelectorAll(".question-answer-form");
    var openQuestionIds = [];
    var params = new URLSearchParams(window.location.search);
    var answeredId = params.get("answered");

    forms.forEach(function (form) {
      var questionId = form.getAttribute("data-question-id");
      openQuestionIds.push(questionId);
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

    // The draft for whichever question the server just confirmed as answered is the only one
    // ever cleared here -- `?answer_failed=<id>` (empty or too-long) deliberately leaves its
    // draft alone, and a plain reload with neither param touches nothing.
    if (answeredId && window.sessionStorage) {
      sessionStorage.removeItem(STORAGE_PREFIX + answeredId);
    }
    pruneClosedDrafts(openQuestionIds);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
