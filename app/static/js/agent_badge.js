// Poll the agent connection badge (FEATURE_SPEC §0.2).
(function () {
  var badge = document.getElementById("agent-badge");
  var label = document.getElementById("agent-badge-label");
  if (!badge) return;
  function refresh() {
    fetch("/api/agent-status")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        badge.classList.toggle("on", !!d.online);
        badge.classList.toggle("off", !d.online);
        if (label) label.textContent = d.label;
      })
      .catch(function () {});
  }
  refresh();
  setInterval(refresh, 5000);
})();
