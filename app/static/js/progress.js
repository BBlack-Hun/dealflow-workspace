// 발송 진행 화면 — 2s polling, counters, per-item log, cancel, retry (FEATURE_SPEC §5 ⑦~⑧).
(function () {
  var jobId = window.DEALFLOW_JOB_ID;
  if (!jobId) return;
  var timer = null;

  // 방 연결 확인 잡은 아무것도 보내지 않는다 → 같은 화면이지만 어휘가 달라야 한다.
  var STATUS_KO = window.DEALFLOW_JOB_VERIFY
    ? { pending: "대기", sending: "확인중", sent: "확인됨", failed: "불일치", canceled: "취소" }
    : { pending: "대기", sending: "발송중", sent: "성공", failed: "실패", canceled: "취소" };

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
    // 관리자가 읽기 전용으로 보고 있으면 버튼 자체가 없다 — 재시도 표시할 곳도 없다.
    var retryBtn = document.getElementById("retry-btn");
    if (retryBtn) retryBtn.hidden = !(terminal && d.counts.failed > 0);

    if (terminal) { if (timer) { clearInterval(timer); timer = null; } }
  }

  function poll() {
    fetch("/api/jobs/" + jobId)
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () {});
  }

  var cancelBtn = document.getElementById("cancel-btn");
  if (cancelBtn) cancelBtn.addEventListener("click", function () {
    var q = window.DEALFLOW_JOB_VERIFY
      ? "확인을 중단하시겠습니까? 남은 건은 미확인으로 남습니다."
      : "발송을 중단하시겠습니까? 아직 발송되지 않은 건은 취소됩니다.";
    if (!confirm(q)) return;
    fetch("/api/jobs/" + jobId + "/cancel", { method: "POST" }).then(poll);
  });
  var retryClickBtn = document.getElementById("retry-btn");
  if (retryClickBtn) retryClickBtn.addEventListener("click", function () {
    fetch("/api/jobs/" + jobId + "/retry", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { if (!timer) timer = setInterval(poll, 2000); poll(); });
  });

  poll();
  timer = setInterval(poll, 2000);
})();
