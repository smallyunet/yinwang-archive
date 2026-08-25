(function () {
  function text(id, value) {
    var element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function showError(message) {
    var loading = document.getElementById("diff-loading");
    var error = document.getElementById("diff-error");
    if (loading) loading.hidden = true;
    if (error) {
      error.textContent = message;
      error.hidden = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var params = new URLSearchParams(window.location.search);
    var dataPath = params.get("data");
    var target = params.get("to");
    if (!dataPath || !target || !/^diffs\/[a-f0-9]{16}\.json$/.test(dataPath)) {
      showError("差异链接不完整，无法载入比较结果。");
      return;
    }

    fetch(dataPath, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        var comparison = data.comparisons && data.comparisons[target];
        if (!comparison) throw new Error("comparison not found");

        document.title = "版本差异｜" + data.title;
        text("diff-title", data.title);
        text("diff-range", comparison.from_date + " → " + comparison.to_date);
        text(
          "diff-summary",
          "新增 " + comparison.counts.added +
            " 段，删除 " + comparison.counts.removed +
            " 段，修改 " + comparison.counts.changed + " 段"
        );

        var back = document.getElementById("diff-back-link");
        if (back) back.href = comparison.to;

        var content = document.getElementById("diff-content");
        if (content) content.innerHTML = comparison.html;

        var loading = document.getElementById("diff-loading");
        if (loading) loading.hidden = true;
      })
      .catch(function () {
        showError("比较结果载入失败，请返回文章后重试。");
      });
  });
})();
