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
  var RESUME_LABEL = window.DEALFLOW_JOB_VERIFY ? "남은 건 이어 확인" : "이어 보내기";
  // 상태 배지에 `queued`·`paused` 같은 영어가 그대로 떴다. 회차가 왜 안 끝났는지
  // 읽는 사람이 알아야 하는 자리라 한글로 바꾼다.
  var JOB_STATUS_KO = {
    draft: "작성 중", queued: "대기 중", running: "보내는 중",
    paused: "멈춤", done: "완료", done_with_errors: "완료(실패 있음)",
    canceled: "중단됨",
  };

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
    badge.textContent = JOB_STATUS_KO[d.status] || d.status;

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

    // 아직 **한 건도 나가지 않은** 회차. 결과 문의 대기 목록이 이 상태로 선다
    // (`services/auto_send.py`) — 발송 프로그램은 `queued` 만 집어가므로,
    // 사람이 [발송 시작] 을 누를 때까지 그대로 기다린다.
    var draft = (d.status === "draft");
    var startBtn = document.getElementById("start-btn");
    if (startBtn) {
      var waiting = d.counts.pending || 0;
      startBtn.hidden = !(draft && waiting > 0);
      // **몇 명에게 나가는지 누르기 전에** 보여야 한다 — 발송은 되돌릴 수 없다.
      // 취소분 재발송·이어 보내기가 같은 이유로 단추에 수를 적는다.
      startBtn.textContent = "발송 시작 (" + waiting + "명)";
      startBtn.dataset.count = waiting;
    }
    var draftNote = document.getElementById("draft-note");
    if (draftNote) draftNote.hidden = !draft;
    renderSchedule(d, draft);
    renderStanding(d);
    // 아직 안 보낸 회차를 [중단] 할 일은 없다 — 중단할 것이 없다.
    var cancelBtn2 = document.getElementById("cancel-btn");
    if (cancelBtn2) cancelBtn2.hidden = draft;

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

    // 이어 보내기 — 끝난 회차에 손도 안 댄 대기 건이 남아 있을 때.
    //
    // **발송 중에는 절대 보이면 안 된다.** 지금 나가고 있는 건을 되살리면
    // 같은 사람에게 두 번 간다. 그래서 terminal 이 아니라 '멈춘 상태' 로 따로
    // 본다 — `paused`(진행이 없어 서버가 세운 회차)도 여기 든다.
    var stopped = terminal || d.status === "paused";
    var resumeBtn = document.getElementById("resume-btn");
    if (resumeBtn) {
      var pending = d.counts.pending || 0;
      resumeBtn.hidden = !(stopped && pending > 0);
      resumeBtn.textContent = RESUME_LABEL + " (" + pending + "명)";
      resumeBtn.dataset.count = pending;
    }

    if (terminal) { if (timer) { clearInterval(timer); timer = null; } }
  }

  function poll() {
    fetch("/api/jobs/" + jobId)
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () {});
  }

  // ── 예약 발송 ──────────────────────────────────────────────────────────
  //
  // [발송 시작] 옆자리다. 사람이 대상을 고르고 회차를 세우는 것까지는 그대로고,
  // **누르면 바로 나가던 것을 정한 시각에 나가게** 한다.
  //
  // **화면은 판정하지 않는다.** 지금이 보낼 때인지, 지나 버린 것인지, 뭐라고
  // 적을지는 전부 서버가 한 곳에서 정해 내려준다(`services/scheduled_send.py`).
  // 여기서 한 번 더 재면 화면에는 `대기 중` 인데 서버는 이미 포기한 상태가 생긴다.
  // 고를 수 있는 시각의 폭. **서버가 내려준 값을 그대로 들고 있는다** —
  // 여기 숫자를 적으면 서버와 두 벌이 되어 한쪽만 고쳐지는 날이 온다.
  var scheduleWindow = { early: 0, late: 0 };

  function renderSchedule(d, draft) {
    var box = document.getElementById("schedule-box");
    if (!box) return;  // 관리자가 읽기 전용으로 보는 중 — 걸 자리가 없다
    var s = d.scheduled || { state: "none" };
    // 아직 안 나간 회차에만 건다. 이미 `queued` 가 된 뒤에는 [중단] 이 맡는다.
    box.hidden = !draft;
    scheduleWindow = { early: Number(s.earliest) || 0, late: Number(s.latest) || 0 };

    var note = document.getElementById("schedule-note");
    if (note) note.textContent = s.sentence || "";
    var booked = (s.state === "waiting" || s.state === "due");

    var hint = document.getElementById("schedule-hint");
    if (hint) {
      hint.textContent = booked
        ? "시각을 다시 고르고 [시각 변경] 을 누르면 바뀝니다."
        : "정한 시각이 되면 저절로 나갑니다 — " + s.earliest + ":00~" + s.latest
          + ":00 안에서 고를 수 있습니다.";
    }

    var at = document.getElementById("schedule-at");
    // 사람이 지금 고치고 있는 칸을 폴링이 덮어쓰면 안 된다 — 2초마다 값이
    // 되돌아가면 시각을 아예 못 고른다. 비어 있을 때만 채운다.
    if (at && !at.value && s.input) at.value = s.input;

    var setBtn = document.getElementById("schedule-btn");
    if (setBtn) setBtn.textContent = booked ? "시각 변경" : "예약";
    var offBtn = document.getElementById("unschedule-btn");
    // 지나 버린 예약도 뗄 수 있어야 한다 — 안 그러면 `예약 시각이 지났습니다`
    // 가 회차 화면에 영영 붙어 있는다.
    if (offBtn) offBtn.hidden = (s.state === "none");

    // [발송 시작] 확인창이 예약을 말할 수 있게 넘겨 둔다.
    var startBtn = document.getElementById("start-btn");
    if (startBtn) startBtn.dataset.booked = booked ? (s.label || "") : "";
  }

  // 큐에 서 있는데 발송기가 안 붙어 있다 — **막힌 것이 아니라 서 있는 것**이다.
  // 예약이 풀려도 그 시각에 PC 가 꺼져 있으면 잡은 그냥 서서 기다린다.
  function renderStanding(d) {
    var box = document.getElementById("standing-note");
    if (!box) return;
    var agent = d.agent || {};
    var waiting = (d.status === "queued" && !agent.online);
    box.hidden = !waiting;
    if (waiting) {
      box.textContent = "발송 프로그램이 연결되어 있지 않습니다 — "
        + "이 회차는 큐에 그대로 서서 기다립니다(막힌 것이 아닙니다). "
        + "그 PC 에서 발송 프로그램을 켜면 이어서 나갑니다.";
    }
  }

  function scheduleFailed(res) {
    alert("예약하지 못했습니다: " + ((res && res.detail) || ""));
  }

  var scheduleBtn = document.getElementById("schedule-btn");
  if (scheduleBtn) scheduleBtn.addEventListener("click", function () {
    var at = document.getElementById("schedule-at");
    var value = (at && at.value) || "";
    if (!value) { alert("보낼 시각을 고르세요."); return; }
    // **화면에서도 막는다.** 서버가 다시 보지만(`scheduled_send.check`), 여기서
    // 걸러 주면 사람이 다시 고르기 전에 왜 안 되는지를 그 자리에서 안다.
    // 폭(09~19시)은 **서버가 내려준 값**이다 — 여기 숫자를 적으면 두 벌이 된다.
    var early = scheduleWindow.early;
    var late = scheduleWindow.late;
    var hour = parseInt(value.slice(11, 13), 10);
    if (early && late && !(hour >= early && hour < late)) {
      alert("예약은 " + early + ":00~" + late + ":00 안에서만 고를 수 있습니다 — "
            + "받는 분들의 업무시간입니다.");
      return;
    }
    fetch("/api/jobs/" + jobId + "/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ at: value })
    })
      .then(function (r) { return r.json().then(function (x) { return { ok: r.ok, d: x }; }); })
      .then(function (res) { if (!res.ok) scheduleFailed(res.d); poll(); })
      .catch(function () { alert("예약 요청 오류"); });
  });

  var unscheduleBtn = document.getElementById("unschedule-btn");
  if (unscheduleBtn) unscheduleBtn.addEventListener("click", function () {
    if (!confirm("예약을 취소합니다.\n회차는 그대로 남아 있어 [발송 시작] 으로 언제든 보낼 수 있습니다.")) return;
    fetch("/api/jobs/" + jobId + "/schedule", { method: "DELETE" })
      .then(function (r) { return r.json().then(function (x) { return { ok: r.ok, d: x }; }); })
      .then(function (res) {
        if (!res.ok) { alert("예약을 취소하지 못했습니다: " + (res.d.detail || "")); return; }
        var at = document.getElementById("schedule-at");
        if (at) at.value = "";
        poll();
      })
      .catch(function () { alert("예약 취소 요청 오류"); });
  });

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
  var resumeClickBtn = document.getElementById("resume-btn");
  if (resumeClickBtn) resumeClickBtn.addEventListener("click", function () {
    var n = Number(resumeClickBtn.dataset.count || 0);
    // 아직 아무에게도 안 간 사람들이라 '다시' 가 아니라 '마저' 다. 그래도 묻는다 —
    // 발송은 되돌릴 수 없고, 몇 명에게 나가는지는 누르기 전에 알아야 한다.
    var q = window.DEALFLOW_JOB_VERIFY
      ? "남은 " + n + "명을 마저 확인합니다. 계속할까요?"
      : "아직 못 보낸 " + n + "명에게 마저 보냅니다.\n이미 발송된 사람에게는 가지 않습니다. 계속할까요?";
    if (!confirm(q)) return;
    fetch("/api/jobs/" + jobId + "/resume", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { if (!timer) timer = setInterval(poll, 2000); poll(); });
  });

  var startClickBtn = document.getElementById("start-btn");
  if (startClickBtn) startClickBtn.addEventListener("click", function () {
    var n = Number(startClickBtn.dataset.count || 0);
    // 예약을 걸어 둔 회차를 지금 보내려는 것이라면 **그 사실을 말한다.**
    // 안 말하면 "예약해 뒀으니 이 단추는 예약을 확인하는 것" 으로 읽고 누른다.
    var booked = startClickBtn.dataset.booked || "";
    // 되돌릴 수 없는 일이라 누르기 전에 한 번 더 묻는다. 화면에 보인 수를 그대로
    // 쓴다 — 여기서 다시 세면 단추와 확인창이 다른 수를 말할 수 있다.
    if (!confirm((booked ? "예약(" + booked + ")을 기다리지 않고 지금 보냅니다.\n" : "")
                 + n + "명에게 지금 보냅니다.\n보낸 뒤에는 되돌릴 수 없습니다. 계속할까요?")) return;
    fetch("/api/jobs/" + jobId + "/start", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { if (!timer) timer = setInterval(poll, 2000); poll(); });
  });

  poll();
  timer = setInterval(poll, 2000);
})();
