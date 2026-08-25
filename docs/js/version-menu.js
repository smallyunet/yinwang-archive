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
    var article = document.getElementById("main-content");
    var preview = document.getElementById("article-diff-preview");
    var previewRange = document.getElementById("article-diff-preview-range");
    var previewContent = document.getElementById("article-diff-preview-content");
    var versionItems = Array.prototype.slice.call(panel.querySelectorAll(".version-item"));
    var diffCache = {};
    var activePreviewItem = null;
    var previewRequest = 0;

    function diffRequest(item) {
      var rawUrl = item && item.getAttribute("data-diff-url");
      if (!rawUrl) return null;
      var url = new URL(rawUrl, window.location.href);
      var dataPath = url.searchParams.get("data");
      var target = url.searchParams.get("to");
      if (!dataPath || !target || !/^diffs\/[a-f0-9]{16}\.json$/.test(dataPath)) return null;
      return { dataPath: dataPath, target: target };
    }

    function loadDiff(dataPath) {
      if (!diffCache[dataPath]) {
        diffCache[dataPath] = fetch(dataPath, { credentials: "same-origin" }).then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return response.json();
        });
      }
      return diffCache[dataPath];
    }

    function positionPreview() {
      if (!article || !preview || preview.hidden) return;
      var rect = article.getBoundingClientRect();
      var left = Math.max(12, rect.left);
      var right = Math.min(window.innerWidth - 12, rect.right);
      var top = Math.max(70, Math.min(rect.top, window.innerHeight - 180));
      preview.style.left = left + "px";
      preview.style.width = Math.min(
        Math.max(280, right - left),
        window.innerWidth - left - 12
      ) + "px";
      preview.style.top = top + "px";
      preview.style.bottom = "16px";
    }

    function hidePreview() {
      previewRequest += 1;
      if (activePreviewItem) activePreviewItem.classList.remove("previewing");
      activePreviewItem = null;
      if (preview) preview.hidden = true;
      document.body.classList.remove("version-diff-previewing");
    }

    function showPreview(item) {
      var request = diffRequest(item);
      if (!request || !article || !preview || !previewContent) {
        hidePreview();
        return;
      }

      if (activePreviewItem && activePreviewItem !== item) {
        activePreviewItem.classList.remove("previewing");
      }
      activePreviewItem = item;
      item.classList.add("previewing");
      var requestId = ++previewRequest;

      loadDiff(request.dataPath)
        .then(function (data) {
          if (requestId !== previewRequest || activePreviewItem !== item) return;
          var comparison = data.comparisons && data.comparisons[request.target];
          if (!comparison) throw new Error("comparison not found");
          if (previewRange) {
            previewRange.textContent = comparison.from_date + " → " + comparison.to_date;
          }
          previewContent.innerHTML = comparison.html;
          preview.hidden = false;
          document.body.classList.add("version-diff-previewing");
          positionPreview();
        })
        .catch(function () {
          if (requestId === previewRequest) hidePreview();
        });
    }

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
      var firstRequest = diffRequest(panel.querySelector(".version-item[data-diff-url]"));
      if (firstRequest) loadDiff(firstRequest.dataPath).catch(function () {});
      if (closeButton) closeButton.focus();
    }

    function closePanel(options) {
      hidePreview();
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

    versionItems.forEach(function (item) {
      item.addEventListener("mouseenter", function () {
        showPreview(item);
      });
      item.addEventListener("mouseleave", function () {
        if (activePreviewItem === item) hidePreview();
      });
      item.addEventListener("focusin", function () {
        showPreview(item);
      });
      item.addEventListener("focusout", function () {
        window.setTimeout(function () {
          if (!item.contains(document.activeElement) && activePreviewItem === item) hidePreview();
        }, 0);
      });
    });

    window.addEventListener("resize", positionPreview);

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
