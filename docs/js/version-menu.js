(function () {
  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  ready(function () {
    var trigger = document.querySelector(".version-menu-trigger");
    var panel = document.getElementById("version-panel");
    var backdrop = document.querySelector(".version-panel-backdrop");
    if (!trigger || !panel || !backdrop) return;

    var closeButton = panel.querySelector(".version-panel-close");

    function focusableElements() {
      return Array.prototype.slice.call(
        panel.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')
      );
    }

    function openPanel() {
      panel.hidden = false;
      backdrop.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      document.body.classList.add("version-panel-open");
      if (closeButton) closeButton.focus();
    }

    function closePanel(options) {
      panel.hidden = true;
      backdrop.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      document.body.classList.remove("version-panel-open");
      if (!options || options.restoreFocus !== false) trigger.focus();
    }

    trigger.addEventListener("click", function () {
      if (panel.hidden) openPanel();
      else closePanel();
    });

    backdrop.addEventListener("click", function () {
      closePanel();
    });

    if (closeButton) {
      closeButton.addEventListener("click", function () {
        closePanel();
      });
    }

    document.addEventListener("keydown", function (event) {
      if (panel.hidden) return;
      if (event.key === "Escape") {
        closePanel();
        return;
      }
      if (event.key !== "Tab") return;

      var focusable = focusableElements();
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  });
})();
