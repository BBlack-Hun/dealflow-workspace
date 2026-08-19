// 발송 진행 화면 — 2s polling, counters, per-item log, cancel, retry (FEATURE_SPEC §5 ⑦~⑧).
(function () {
  var jobId = window.DEALFLOW_JOB_ID;
  if (!jobId) return;
  var timer = null;

  var STATUS_KO = { pending: "대기", sending: "발송중", sent: "성공", failed: "실패", canceled: "취소" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  function render(d) {
    document.getElementById("c-pending").textContent = d.counts.pending;
    document.getElementById("c-sending").textContent = d.counts.sending;
    document.getElementById("c-sent").textContent = d.counts.sent;
    document.getElementById("c-failed").textContent = d.counts.failed;

    var badge = document.getElementById("job-status-badge");
    badge.textContent = d.status;

    var body = document.getElementById("log-body");
    body.innerHTML = d.items.map(function (i) {
      return "<tr>" +
        "<td>" + esc(i.contact_name) + "</td>" +
        "<td>" + esc(i.room_name) + "</td>" +
        '<td class="st st-' + i.status + '">' + (STATUS_KO[i.status] || i.status) + "</td>" +
        "<td>" + (i.retry_count || 0) + "</td>" +
        "<td>" + esc(i.error || i.sent_at || "") + "</td>" +
        "</tr>";
    }).join("");

    var terminal = (d.status === "done" || d.status === "done_with_errors" || d.status === "canceled");
    var retryBtn = document.getElementById("retry-btn");
    retryBtn.hidden = !(terminal && d.counts.failed > 0);

    if (terminal) { if (timer) { clearInterval(timer); timer = null; } }
  }

  function poll() {
    fetch("/api/jobs/" + jobId)
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () {});
  }

  document.getElementById("cancel-btn").addEventListener("click", function () {
    if (!confirm("발송을 중단하시겠습니까? 아직 발송되지 않은 건은 취소됩니다.")) return;
    fetch("/api/jobs/" + jobId + "/cancel", { method: "POST" }).then(poll);
  });
  document.getElementById("retry-btn").addEventListener("click", function () {
    fetch("/api/jobs/" + jobId + "/retry", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { if (!timer) timer = setInterval(poll, 2000); poll(); });
  });

  poll();
  timer = setInterval(poll, 2000);
})();
