/* 스타트업 안내 카톡 — 고르고 · 미리 보고 · 대기 목록을 세운다.
 * (node tests/js/startup_msg_test.js)
 *
 * ## 여기서 판단하지 않는다  ★
 *
 * 어느 줄을 고를 수 있는지는 **서버가 정해서 그려 준다** — 못 고르는 줄에는
 * 체크상자 자체가 없다(`services/startup_outreach.rows`). 채움말(`{대표명}` …)도
 * 여기서 채우지 않고 서버에 묻는다(`/api/startup-msg/preview` →
 * `startup_outreach.render`). 같은 규칙을 자바스크립트로 한 벌 더 적으면 한쪽만
 * 고쳐지는 날 미리보기와 대표가 받는 글이 갈린다.
 *
 * ## 보이는 줄만 보낸다  ★
 *
 * 거르개(계약여부 · 검색)로 감춘 줄은 **체크를 푼다.** 감춘 채 체크가 남아
 * 있으면 단추의 `N곳` 에 화면에 없는 줄이 섞이고, 사람은 보이는 줄만 보고
 * 누른다 — 안 본 기업에 나간다.
 */
(function () {
  "use strict";

  var table = document.getElementById("msg-table");
  if (!table) return;

  var bodyBox = document.getElementById("msg-body");
  var sendBtn = document.getElementById("msg-send-btn");
  var allBox = document.getElementById("msg-all");
  var contractSel = document.getElementById("msg-contract");
  var search = document.getElementById("msg-search");
  var errorBox = document.getElementById("msg-error");

  function rows() { return table.querySelectorAll("tr.msg-row"); }
  function topic() { return bodyBox ? bodyBox.getAttribute("data-topic") : ""; }

  function setError(text) {
    if (errorBox) errorBox.textContent = text || "";
  }

  // ── 거르기 ────────────────────────────────────────────────────────────
  function applyFilter() {
    var want = contractSel ? contractSel.value : "";
    var q = search ? String(search.value || "").trim().toLowerCase() : "";
    Array.prototype.forEach.call(rows(), function (tr) {
      var okContract = !want || tr.getAttribute("data-contract") === want;
      var okSearch = !q || (tr.getAttribute("data-search") || "").indexOf(q) >= 0;
      tr.hidden = !(okContract && okSearch);
      if (tr.hidden) {
        var cb = tr.querySelector(".msg-pick");
        if (cb) cb.checked = false;     // 보이는 줄만 보낸다(머리말)
      }
    });
    refresh();
  }

  // ── 고른 줄 ───────────────────────────────────────────────────────────
  function picked() {
    var out = [];
    Array.prototype.forEach.call(rows(), function (tr) {
      if (tr.hidden) return;
      var cb = tr.querySelector(".msg-pick");
      if (cb && cb.checked) out.push(parseInt(cb.value, 10));
    });
    return out;
  }

  function refresh() {
    var n = picked().length;
    if (sendBtn) {
      // **몇 곳에 가는지 단추에 적는다** — 누른 뒤에 아는 것은 늦다.
      sendBtn.textContent = n + "곳 대기 목록 만들기";
      sendBtn.disabled = n === 0;
    }
  }

  table.addEventListener("change", function (e) {
    if (e.target && e.target.classList && e.target.classList.contains("msg-pick")) refresh();
  });
  if (allBox) {
    allBox.addEventListener("change", function () {
      Array.prototype.forEach.call(rows(), function (tr) {
        var cb = tr.querySelector(".msg-pick");
        if (cb && !tr.hidden) cb.checked = !!allBox.checked;
      });
      refresh();
    });
  }
  if (contractSel) contractSel.addEventListener("change", applyFilter);
  if (search) search.addEventListener("input", applyFilter);

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  // ── 미리보기 — 서버가 채운 글을 그대로 보여 준다 ────────────────────────
  var previewBtn = document.getElementById("msg-preview-btn");
  var previewBox = document.getElementById("msg-preview");
  var previewList = document.getElementById("msg-preview-list");
  var previewNote = document.getElementById("msg-preview-note");

  function renderPreview(d) {
    if (!previewBox || !previewList) return;
    while (previewList.children && previewList.children.length) {
      previewList.removeChild(previewList.children[0]);
    }
    (d.previews || []).forEach(function (p) {
      var item = document.createElement("div");
      item.className = "msg-preview-item";
      var head = document.createElement("b");
      head.textContent = [p.firm, p.name].filter(Boolean).join(" · ") +
        (p.room ? "  →  " + p.room : "");
      var text = document.createElement("pre");
      // 글자 그대로 — 대표가 받는 글이다. HTML 로 넣지 않는다.
      text.textContent = p.message;
      item.appendChild(head);
      item.appendChild(text);
      previewList.appendChild(item);
    });
    if (previewNote) {
      previewNote.textContent = d.sample
        ? "— 아직 아무 곳도 안 골라 지어낸 줄로 보여 줍니다"
        : "— 고른 " + (d.previews || []).length + "곳에 이 글이 나갑니다";
    }
    previewBox.hidden = false;
  }

  if (previewBtn) {
    previewBtn.addEventListener("click", function () {
      setError("");
      post("/api/startup-msg/preview",
           { topic: topic(), body: bodyBox ? bodyBox.value : "", contact_ids: picked() })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "미리보기 실패"); return; }
          renderPreview(res.d);
        })
        .catch(function () { setError("미리보기 오류"); });
    });
  }

  // ── 대기 목록 만들기 ───────────────────────────────────────────────────
  if (sendBtn) {
    sendBtn.addEventListener("click", function () {
      var ids = picked();
      if (!ids.length) return;
      setError("");
      var whenBox = document.getElementById("msg-when");
      var titleBox = document.getElementById("msg-title");
      if (!window.confirm(ids.length + "곳짜리 대기 목록을 만듭니다.\n" +
          "아직 보내지 않습니다 — 진행 화면에서 [발송 시작] 을 눌러야(또는 고른 " +
          "시각이 되어야) 나갑니다.")) return;
      sendBtn.disabled = true;
      post("/api/startup-msg/send", {
        topic: topic(),
        body: bodyBox ? bodyBox.value : "",
        contact_ids: ids,
        days: parseInt(sendBtn.getAttribute("data-days") || "0", 10) || 0,
        title: titleBox ? titleBox.value : "",
        scheduled_at: whenBox ? whenBox.value : ""
      })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "대기 목록을 만들지 못했습니다"); refresh(); return; }
          window.location.href = res.d.href || ("/jobs/" + res.d.job_id);
        })
        .catch(function () { setError("대기 목록 만들기 오류"); refresh(); });
    });
  }

  // ── 방 확인 전 줄 — 방 제목 저장 · [방 연결 확인] ─────────────────────
  //
  // 저장은 표에서 칸을 고칠 때와 **같은 길**이다(`PATCH /api/contacts/{id}`) —
  // 글자가 바뀌면 확인이 풀리는 규칙이 거기 있다(`services/room_joined`).
  var noroom = document.getElementById("msg-noroom");
  if (noroom) {
    noroom.addEventListener("click", function (e) {
      var btn = e.target && e.target.closest ? e.target.closest(".room-save") : null;
      if (!btn) return;
      e.preventDefault();
      var row = btn.closest("tr");
      var input = row ? row.querySelector(".room-input") : null;
      if (!input) return;
      fetch("/api/contacts/" + btn.getAttribute("data-id"), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kakao_room_name: input.value })
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "방 제목 저장 실패"); return; }
          window.location.reload();
        })
        .catch(function () { setError("방 제목 저장 오류"); });
    });
  }
  var verifyBtn = document.getElementById("msg-verify-btn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", function () {
      var ids = (verifyBtn.getAttribute("data-ids") || "").split(",")
        .filter(Boolean).map(function (v) { return parseInt(v, 10); });
      if (!ids.length) return;
      if (!window.confirm(ids.length + "곳의 카톡방을 확인합니다.\n" +
          "카카오톡이 켜져 있어야 하며, 확인 중에는 PC 조작을 멈춰주세요.\n" +
          "(문구는 전송하지 않습니다)")) return;
      post("/api/contacts/verify-rooms", { contact_ids: ids })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "확인 요청 실패"); return; }
          window.location.href = "/jobs/" + res.d.job_id;
        })
        .catch(function () { setError("확인 요청 오류"); });
    });
  }

  refresh();
})();
