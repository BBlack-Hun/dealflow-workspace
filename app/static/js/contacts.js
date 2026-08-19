// 내 투자사 — 상세 패널 · CRUD · 방 연결 확인 (FEATURE_SPEC §3, ROADMAP 2.2/2.5)
(function () {
  "use strict";

  var FIELDS = ["name", "title", "firm", "group_name", "kakao_room_name", "invited_status",
    "status", "stages", "sectors", "round_size", "email", "phone", "memo"];
  var CHECKS = ["channel_kakao", "channel_email"];
  var KIND_KO = {
    deal_intro: "딜소개", ir_request: "IR 요청", meeting: "미팅",
    memo: "메모", ir_delivery: "IR 전달"
  };

  var panel = document.getElementById("detail-panel");
  var table = document.getElementById("contacts-table");
  var msg = document.getElementById("detail-msg");
  var current = null;   // null = 새 담당자 추가 모드
  var filters = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }
  function el(id) { return document.getElementById(id); }
  function setMsg(text, isError) {
    msg.textContent = text || "";
    msg.className = "hint" + (isError ? " error" : "");
  }

  function openPanel(title) {
    el("detail-title").textContent = title;
    panel.hidden = false;
    showTab("info");
  }

  function showTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll(".detail-tab"), function (b) {
      b.classList.toggle("active", b.getAttribute("data-tab") === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-panel]"), function (p) {
      p.hidden = p.getAttribute("data-panel") !== name;
    });
  }

  function fillForm(c) {
    FIELDS.forEach(function (f) { if (el("f-" + f)) el("f-" + f).value = c[f] || ""; });
    CHECKS.forEach(function (f) { el("f-" + f).checked = !!c[f]; });
  }

  function readForm() {
    var body = {};
    FIELDS.forEach(function (f) { if (el("f-" + f)) body[f] = el("f-" + f).value.trim(); });
    CHECKS.forEach(function (f) { body[f] = el("f-" + f).checked ? 1 : 0; });
    return body;
  }

  // 활동 이력은 **월 단위로 묶어** 보여준다. 시트가 월별 컬럼이었기 때문에
  // 사용자의 머릿속 단위도 '8월에 뭘 보냈지'다. 회차는 '몇째 주·요일·몇 개사'로 읽힌다.
  function renderTimeline(items) {
    var list = el("timeline");
    if (!items.length) {
      list.innerHTML = '<li class="muted">기록이 없습니다.</li>';
      return;
    }
    items.sort(function (a, b) {
      var x = a.date || a.month || "", y = b.date || b.month || "";
      return x < y ? 1 : (x > y ? -1 : 0);
    });

    var html = "";
    var lastMonth = null;
    items.forEach(function (t) {
      var month = t.month || (t.date ? t.date.slice(0, 7) : "");
      if (month !== lastMonth) {
        lastMonth = month;
        html += '<li class="tl-month">' + esc(monthLabel(month)) + "</li>";
      }
      html += '<li class="tl-item tl-' + esc(t.kind) + '">' +
        '<span class="tl-date tabular">' + esc(dayLabel(t)) + "</span>" +
        '<span class="tl-kind">' + esc(KIND_KO[t.kind] || t.kind) + "</span>" +
        '<span class="tl-body">' + bodyHtml(t) + "</span>" +
        (t.source === "import" ? '<span class="tl-src">시트</span>' : "") +
        "</li>";
    });
    list.innerHTML = html;
  }

  function monthLabel(month) {
    if (!month) return "날짜 미상";
    var parts = month.split("-");
    return parts.length > 1 ? parts[0] + "년 " + parseInt(parts[1], 10) + "월" : month;
  }

  function dayLabel(t) {
    if (!t.date) return "";
    var d = t.date.slice(5).replace("-", ".");
    return d + (t.weekday ? "(" + t.weekday + ")" : "");
  }

  function bodyHtml(t) {
    var head = "";
    if (t.week) head += '<span class="tl-week">' + t.week + "주차</span> ";
    if (t.company_count) head += "<b>" + t.company_count + "개사</b> ";
    if (t.companies && t.companies.length) {
      // 딜 기업 DB에 있는 기업은 표시만 다르게(없는 기업이 더 많아 오류로 다루지 않는다).
      return head + t.companies.map(function (c) {
        return '<span class="tl-co' + (c.known ? " known" : "") + '">' + esc(c.name) + "</span>";
      }).join(" ");
    }
    return head + esc(t.content);
  }

  function loadContact(id) {
    fetch("/api/contacts/" + id)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.contact) { setMsg("담당자를 불러오지 못했습니다", true); return; }
        current = d.contact.id;
        fillForm(d.contact);
        renderTimeline(d.timeline || []);
        openPanel(d.contact.name + " " + (d.contact.title || "") + " · " + (d.contact.firm || ""));
        setMsg("");
      })
      .catch(function () { setMsg("조회 오류", true); });
  }

  function save() {
    var body = readForm();
    if (!body.name) { setMsg("담당자명을 입력하세요", true); return; }
    var url = current ? "/api/contacts/" + current : "/api/contacts";
    fetch(url, {
      method: current ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { setMsg(res.d.detail || "저장 실패", true); return; }
        // 표의 집계값(최근 딜소개·반응)은 서버에서 만든다 → 새로고침이 가장 정확하다.
        window.location.reload();
      })
      .catch(function () { setMsg("저장 오류", true); });
  }

  function remove() {
    if (!current) { panel.hidden = true; return; }
    if (!confirm("이 담당자를 삭제할까요? 활동 이력도 함께 지워집니다.\n" +
      "(이직·투자사 변경이면 삭제 대신 '검토중단' 을 권합니다 — 이력이 남습니다)")) return;
    fetch("/api/contacts/" + current, { method: "DELETE" })
      .then(function () { window.location.reload(); })
      .catch(function () { setMsg("삭제 오류", true); });
  }

  function visibleIds() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr.data-row"))
      .filter(function (tr) { return !tr.hidden; })
      .map(function (tr) { return parseInt(tr.getAttribute("data-id"), 10); });
  }

  function verify(ids, label) {
    if (!ids.length) { alert("확인할 담당자가 없습니다."); return; }
    if (!confirm(label + " " + ids.length + "명의 카톡방 이름을 확인합니다.\n" +
      "카카오톡이 켜져 있어야 하며, 확인 중에는 PC 조작을 멈춰주세요.\n" +
      "(문구는 전송하지 않습니다)")) return;
    fetch("/api/contacts/verify-rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_ids: ids })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "확인 요청 실패"); return; }
        window.location.href = "/jobs/" + res.d.job_id;
      })
      .catch(function () { alert("확인 요청 오류"); });
  }

  // ── 이벤트 ────────────────────────────────────────────────────────────────
  if (table) {
    table.addEventListener("click", function (e) {
      var tr = e.target.closest ? e.target.closest("tr.data-row") : null;
      if (!tr) return;
      if (e.target.tagName === "A") return;      // 바로가기 링크는 그대로
      loadContact(parseInt(tr.getAttribute("data-id"), 10));
    });
  }

  el("detail-close").addEventListener("click", function () { panel.hidden = true; });
  el("save-btn").addEventListener("click", save);
  el("delete-btn").addEventListener("click", remove);
  el("verify-one-btn").addEventListener("click", function () {
    if (current) verify([current], "선택한 담당자");
  });
  el("verify-btn").addEventListener("click", function () {
    verify(visibleIds(), "현재 목록의");
  });
  el("add-btn").addEventListener("click", function () {
    current = null;
    fillForm({ status: "active", channel_kakao: 1 });
    el("f-channel_kakao").checked = true;
    openPanel("담당자 추가");
    setMsg("투자사명을 넣으면 카톡방 이름이 자동 생성됩니다(비워둘 경우).");
  });
  Array.prototype.forEach.call(document.querySelectorAll(".detail-tab"), function (b) {
    b.addEventListener("click", function () { showTab(b.getAttribute("data-tab")); });
  });
  var density = el("density-toggle");
  if (density) {
    density.addEventListener("change", function () {
      table.classList.toggle("dense", density.checked);
    });
  }

  if (window.DealflowFilters && table) {
    filters = window.DealflowFilters.init({ table: "#contacts-table" });
  }
})();
