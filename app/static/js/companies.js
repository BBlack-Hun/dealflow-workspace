// 딜 기업 DB — 검색·필터 + 상세 편집.
//
// 이 화면의 목적은 목록 구경이 아니라 "왜 이 기업이 소개 목록에 안 뜨는가"를
// 그 자리에서 고치는 것이다. 그래서 저장하면 소개 가능 여부를 즉시 다시 그린다.
(function () {
  var table = document.getElementById("co-table");
  if (!table) return;

  var panel = document.getElementById("co-panel");
  var search = document.getElementById("co-search");
  var note = document.getElementById("co-note");
  var status = document.getElementById("co-status");
  var current = null;   // 편집 중인 기업 id (null = 새로 추가)
  var filter = "";

  var FIELDS = ["name", "sector_major", "sector_minor", "series", "one_liner",
    "revenue_recent", "funding_total", "raise_target", "pre_value",
    "competitiveness", "funding_status", "ir_drive_url",
    "contract_status", "contract_month", "summary_status", "note"];

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }

  // ── 검색 · 컬럼 필터 ───────────────────────────────────────
  // 컬럼 필터(엑셀의 자동 필터와 같은 방식)는 공통 컴포넌트가 맡고,
  // 검색창은 그 위에 AND 로 얹는다. 둘이 각자 tr.hidden 을 만지면
  // 검색과 필터가 번갈아 서로를 지운다.
  var filters = null;

  function textMatch(tr) {
    var q = (search.value || "").trim().toLowerCase();
    return !q || (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
  }

  function apply() {
    if (filters) { filters.apply(); return; }
    rows().forEach(function (tr) { tr.hidden = !textMatch(tr); });
    afterApply();
  }

  function afterApply() {
    var total = rows().length;
    var shown = rows().filter(function (tr) { return !tr.hidden; }).length;
    renumber();
    if (shown !== total) {
      note.hidden = false;
      note.textContent = shown + " / " + total + "개 표시 중";
    } else {
      note.hidden = true;
    }
  }

  // 행 번호는 '보이는 것' 기준으로 매긴다 — 걸러낸 뒤 몇 개인지 세기 위해서다.
  function renumber() {
    var n = 0;
    rows().forEach(function (tr) {
      var cell = tr.querySelector(".rowno");
      if (!cell) return;
      if (tr.hidden) { cell.textContent = ""; return; }
      n += 1;
      cell.textContent = n;
    });
  }

  search.addEventListener("input", apply);

  if (window.DealflowFilters) {
    filters = window.DealflowFilters.init({
      table: "#co-table",
      unit: "개",
      extra: textMatch,
      onChange: afterApply
    });
  }

  // ── 상세 편집 ──────────────────────────────────────────────
  function el(id) { return document.getElementById(id); }

  function fill(data) {
    FIELDS.forEach(function (f) {
      var input = el("f-" + f);
      if (input) input.value = data[f] === null || data[f] === undefined ? "" : data[f];
    });
    el("f-is_top_deal").checked = !!data.is_top_deal;
    setStatus(data);
  }

  function setStatus(data) {
    if (data && data.introducible) {
      status.className = "hint ok";
      status.textContent = "✅ 소개 가능 — 발송 화면 목록에 뜹니다.";
    } else {
      status.className = "hint warn";
      status.textContent = "⚠ 소개 불가" +
        (data && data.blocked_reason ? " — " + data.blocked_reason : "") +
        " · 분야/한줄소개와 숫자 하나가 있어야 문구를 만들 수 있습니다.";
    }
  }

  function close() {
    panel.hidden = true;
    document.getElementById("co-backdrop").hidden = true;
  }

  function open(id) {
    current = id;
    panel.hidden = false;
    document.getElementById("co-backdrop").hidden = false;
    el("co-delete").hidden = !id;
    if (!id) {
      el("co-title").textContent = "기업 추가";
      fill({ contract_status: "no", summary_status: "draft" });
      el("f-name").focus();
      return;
    }
    el("co-title").textContent = "불러오는 중…";
    fetch("/api/companies/" + id)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        el("co-title").textContent = d.name;
        fill(d);
      });
  }

  function collect() {
    var body = {};
    FIELDS.forEach(function (f) {
      var input = el("f-" + f);
      if (!input) return;
      var v = input.value.trim();
      if (input.type === "number") body[f] = v === "" ? null : parseInt(v, 10);
      else body[f] = v;
    });
    body.is_top_deal = el("f-is_top_deal").checked;
    return body;
  }

  el("co-add").addEventListener("click", function () { open(null); });
  el("co-close").addEventListener("click", close);
  el("co-cancel").addEventListener("click", close);
  el("co-backdrop").addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) close();
  });

  table.addEventListener("click", function (e) {
    if (!e.target.classList.contains("js-co-edit")) return;
    open(parseInt(e.target.closest("tr").getAttribute("data-id"), 10));
  });

  el("co-save").addEventListener("click", function () {
    var body = collect();
    if (!body.name) { alert("기업명을 입력하세요."); return; }
    var url = current ? "/api/companies/" + current : "/api/companies";
    fetch(url, {
      method: current ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "저장 실패"); return; }
        window.location.reload();   // 표의 소개 가능 여부까지 다시 그려야 한다
      })
      .catch(function () { alert("저장 요청 오류"); });
  });

  el("co-delete").addEventListener("click", function () {
    if (!current) return;
    if (!confirm("이 기업을 삭제할까요?\n이미 보낸 회차에 들어간 기업은 삭제할 수 없습니다.")) return;
    fetch("/api/companies/" + current, { method: "DELETE" })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "삭제 실패"); return; }
        window.location.reload();
      });
  });

  apply();
})();

// ── 표에서 눌러 바로 고치기 뒤처리 ────────────────────────────────────
//
// 매출 하나를 채우면 '소개 가능'이 ⚠ 에서 ● 로 바뀔 수 있다. 새로고침해야
// 바뀌면, 297개를 채우는 동안 뭐가 아직 모자란지 알 수 없다.
// PATCH 응답이 introducible · blocked_reason 을 돌려주므로 그 자리에서 고쳐 그린다.
(function () {
  var table = document.getElementById("co-table");
  if (!table) return;

  table.addEventListener("inline-saved", function (e) {
    var data = e.detail.data || {};
    if (!("introducible" in data)) return;
    var cell = e.detail.row.querySelector(".ready-cell");
    if (!cell) return;

    var badge = document.createElement("span");
    if (data.introducible) {
      badge.className = "room-badge ok";
      badge.textContent = "● 가능";
    } else {
      badge.className = "room-badge warn";
      badge.textContent = "⚠ " + (data.blocked_reason || "내용 부족");
      badge.title = data.blocked_reason || "";
    }
    cell.textContent = "";
    cell.appendChild(badge);

    // 필터가 이 값으로 거르고 있다 — 행의 값도 같이 맞춰 둔다.
    e.detail.row.setAttribute("data-f-ready",
      data.introducible ? "● 소개 가능" : "⚠ 내용 부족");
  });
})();

// 단계는 표에 이름만 보인다 — 괄호 안 설명은 297행에 똑같이 반복되는 참고문이라
// 칸을 통째로 잡아먹는다. 저장한 뒤에도 짧은 이름으로 되돌려 그린다.
(function () {
  var table = document.getElementById("co-table");
  if (!table) return;

  table.addEventListener("inline-saved", function (e) {
    var cell = e.detail.cell;
    if (!cell.hasAttribute("data-value")) return;
    var full = cell.getAttribute("data-value") || "";
    cell.textContent = full.split(" (")[0].trim();
    cell.title = full;
  });
})();
