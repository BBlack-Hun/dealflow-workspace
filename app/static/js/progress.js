// 발송 진행 화면 — 2s polling, counters, per-item log, cancel, retry (FEATURE_SPEC §5 ⑦~⑧).
(function () {
  var jobId = window.DEALFLOW_JOB_ID;
  if (!jobId) return;
  var timer = null;

  // 방 연결 확인 잡은 아무것도 보내지 않는다 → 같은 화면이지만 어휘가 달라야 한다.
  var STATUS_KO = window.DEALFLOW_JOB_VERIFY
    ? { pending: "대기", sending: "확인중", sent: "확인됨", failed: "불일치", canceled: "취소" }
    : { pending: "대기", sending: "발송중", sent: "성공", failed: "실패", canceled: "취소" };
  var RESEND_LABEL = window.DEALFLOW_JOB_VERIFY ? "취소분 재확인" : "취소분 재발송";

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

    // 취소분 재발송 — **몇 명에게 다시 나가는지 누르기 전에** 보여야 한다.
    // 발송은 되돌릴 수 없어서, 누른 뒤에 숫자를 아는 것은 늦다.
    var resendBtn = document.getElementById("resend-canceled-btn");
    if (resendBtn) {
      var canceled = d.counts.canceled || 0;
      resendBtn.hidden = !(terminal && canceled > 0);
      resendBtn.textContent = RESEND_LABEL + " (" + canceled + "명)";
      // 확인창에서 다시 세지 않고 화면에 보인 숫자를 그대로 쓴다 — 버튼에 적힌 수와
      // 확인창의 수가 다르면 어느 쪽을 믿어야 할지 알 수 없다.
      resendBtn.dataset.count = canceled;
    }

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
    // 지금 보내는 중인 건은 이미 카톡으로 나갔을 수 있다 — 나간 것은 되돌릴 수
    // 없다. "중단했으니 아무도 못 받았다" 고 알면 그 한 명에게 다시 보내게 된다.
    // 화면에 이미 떠 있는 숫자를 그대로 읽는다. 따로 담아 두면 2초 폴링과
    // 어긋나서 화면과 확인창이 다른 수를 말하게 된다.
    var el = document.getElementById("c-sending");
    var inFlight = el ? (parseInt(el.textContent, 10) || 0) : 0;
    var q = window.DEALFLOW_JOB_VERIFY
      ? "확인을 중단하시겠습니까? 남은 건은 미확인으로 남습니다."
      : "발송을 중단하시겠습니까? 아직 발송되지 않은 건은 취소됩니다."
        + (inFlight ? "\n지금 보내는 중인 " + inFlight + "건은 이미 나갔을 수 있습니다." : "");
    if (!confirm(q)) return;
    fetch("/api/jobs/" + jobId + "/cancel", { method: "POST" }).then(poll);
  });
  var retryClickBtn = document.getElementById("retry-btn");
  if (retryClickBtn) retryClickBtn.addEventListener("click", function () {
    fetch("/api/jobs/" + jobId + "/retry", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { if (!timer) timer = setInterval(poll, 2000); poll(); });
  });
  var resendClickBtn = document.getElementById("resend-canceled-btn");
  if (resendClickBtn) resendClickBtn.addEventListener("click", function () {
    var n = Number(resendClickBtn.dataset.count || 0);
    // 실패 재시도와 달리 한 번 더 묻는다 — 중단했던 회차를 다시 내보내는 일이라
    // 잘못 누르면 이미 그만두기로 한 사람들에게 문구가 나간다.
    var q = window.DEALFLOW_JOB_VERIFY
      ? n + "명을 다시 확인합니다. 계속할까요?"
      : n + "명에게 다시 보냅니다.\n이미 발송된 사람에게는 다시 보내지 않습니다. 계속할까요?";
    if (!confirm(q)) return;
    fetch("/api/jobs/" + jobId + "/resend-canceled", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { if (!timer) timer = setInterval(poll, 2000); poll(); });
  });

  poll();
  timer = setInterval(poll, 2000);
})();
