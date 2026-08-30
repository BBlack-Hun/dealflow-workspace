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
  // 무엇을 지우는지 확인창에 **이름**이 나와야 한다. 되돌릴 수 없는 일이라
  // "이 기업" 만으로는 어느 줄에서 열었는지 확신할 수 없다
  // (투자컨설턴트 현황이 같은 이유로 이름을 대고 묻는다).
  var currentName = "";
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

  // 화면은 억, 저장은 백만원. DB 는 백만원으로 쌓여 있다(임포트·딜소개 문구가
  // 그 단위를 쓴다). 사람에게는 어디서도 백만원을 보여주지 않는다 — 표는 억인데
  // 수정 창만 백만원이면 같은 값이 100배 차이로 보인다.
  var EOK_FIELDS = ["revenue_recent", "funding_total", "raise_target", "pre_value"];

  function toEok(v) {
    if (v === null || v === undefined || v === "") return "";
    var n = Number(v) / 100;
    return String(Math.round(n * 10) / 10);      // 18.3 · 150 · 0.2
  }

  function toStored(v) {
    if (v === "" || v === null || v === undefined) return null;
    var n = Number(v);
    return isNaN(n) ? null : Math.round(n * 100);
  }

  function fill(data) {
    FIELDS.forEach(function (f) {
      var input = el("f-" + f);
      if (!input) return;
      var raw = data[f] === null || data[f] === undefined ? "" : data[f];
      input.value = EOK_FIELDS.indexOf(f) >= 0 ? toEok(raw) : raw;
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
    // 관리자가 아니면 단추 자체가 없다(companies.html 이 안 그린다).
    if (el("co-delete")) el("co-delete").hidden = !id;
    if (!id) {
      el("co-title").textContent = "기업 추가";
      currentName = "";
      // `no` 는 **화면에 없는 값**이다(option 은 none/free/paid/review/blocked).
      // 없는 값을 넣으면 select 가 고른 것 없는 상태가 되고, 그대로 [저장]하면
      // 빈 값이 날아가 NOT NULL 인 칸에서 저장 전체가 500 이 났다.
      fill({ contract_status: "none", summary_status: "draft" });
      el("f-name").focus();
      return;
    }
    el("co-title").textContent = "불러오는 중…";
    fetch("/api/companies/" + id)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        el("co-title").textContent = d.name;
        currentName = d.name || "";
        fill(d);
      });
  }

  function collect() {
    var body = {};
    FIELDS.forEach(function (f) {
      var input = el("f-" + f);
      if (!input) return;
      var v = input.value.trim();
      if (EOK_FIELDS.indexOf(f) >= 0) body[f] = toStored(v);
      else if (input.type === "number") body[f] = v === "" ? null : parseInt(v, 10);
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

  // 관리자가 아니면 단추가 아예 없다 — 있을 때만 건다.
  if (el("co-delete")) el("co-delete").addEventListener("click", function () {
    if (!current) return;
    // **무엇을 지우는지 이름을 대고 묻는다.** 되돌릴 수 없다.
    // 되돌릴 길(딜소개 불가)을 같이 알려 준다 — 지우는 것 말고도 발송
    // 목록에서 빼는 방법이 있다는 것을 여기서 처음 아는 사람이 많다.
    if (!confirm("'" + (currentName || "이 기업") + "' 을 삭제할까요? 되돌릴 수 없습니다.\n" +
      "(딜소개를 보낸 적이 있으면 이력이 깨지므로 삭제되지 않습니다 — " +
      "계약여부를 '딜소개 불가' 로 두면 발송 목록에서 빠집니다)")) return;
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

// 계약여부 — 표에는 **말**이 보이고 저장되는 것은 값이다. 저장 뒤에는
// **응답이 준 말**로 되그린다. 누른 글자를 그대로 두면, 라우터가 맞춰 넣은
// 값(`딜소개불가` → `blocked`)과 화면 글자가 갈려 새로고침 때 다른 말이 나온다.
//
// `딜소개 불가` 로 바꾸면 그 줄에 표시가 붙어야 한다. 이 표시가 곧 "발송
// 화면에서 빠졌다" 는 뜻이라, 새로고침해야 보이면 바꾼 것이 걸렸는지 알 수 없다.
(function () {
  var table = document.getElementById("co-table");
  if (!table) return;

  table.addEventListener("inline-saved", function (e) {
    var data = e.detail.data || {};
    if (!("contract_label" in data)) return;
    var cell = e.detail.cell;
    if (cell.getAttribute("data-field") !== "contract_status") return;

    cell.textContent = data.contract_label;
    cell.title = data.contract_label;
    var row = e.detail.row;
    if (!row) return;
    // 필터도 **맞춘 말**로 거른다. 누른 그대로 두면 같은 뜻이 목록에 두 벌로
    // 갈려(`딜소개불가` · `딜소개 불가`), 한쪽을 골랐을 때 그 기업만 사라진다.
    if (row.hasAttribute("data-f-contract")) {
      row.setAttribute("data-f-contract", data.contract_label);
    }
    row.classList.toggle("blocked-row", !!data.blocked);
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
    var short = full.split(" (")[0].trim();
    cell.textContent = short;
    cell.title = full;
    // 필터도 **짧은 이름**으로 거른다(다른 296행이 그렇게 실려 있다).
    // 고른 그대로 적어 두면 같은 단계가 목록에 두 벌로 갈려서,
    // 짧은 쪽을 골랐을 때 방금 고친 그 기업만 사라진다.
    var row = e.detail.row;
    if (row && row.hasAttribute("data-f-series")) {
      row.setAttribute("data-f-series", short);
    }
  });
})();

// 핵심/TOP Deal 을 비우면 행에는 `일반` 이 실린다 — 표를 처음 그릴 때와 같은
// 규칙이다. 빈 값 그대로 두면 같은 뜻이 필터 목록에 `일반` 과 `(비어 있음)`
// 두 벌로 갈린다.
(function () {
  var table = document.getElementById("co-table");
  if (!table) return;
  table.addEventListener("inline-saved", function (e) {
    var row = e.detail.row;
    if (!row || !row.hasAttribute("data-f-top")) return;
    if (!(row.getAttribute("data-f-top") || "").trim()) {
      row.setAttribute("data-f-top", "일반");
    }
  });
})();

// 핵심/TOP Deal — 시트에서는 이 칸에 ★ 를 찍는다. 눌러서 켜고 끈다.
(function () {
  var table = document.getElementById("co-table");
  if (!table) return;
  table.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-top");
    if (!btn) return;
    var row = btn.closest("tr");
    var on = !btn.classList.contains("on");
    fetch("/api/companies/" + row.getAttribute("data-id"), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_top_deal: on })
    }).then(function (r) {
      if (!r.ok) throw new Error();
      btn.classList.toggle("on", on);
      btn.textContent = on ? "★ 핵심" : "☆";
      row.setAttribute("data-f-top", on ? "★ 핵심" : "일반");
    }).catch(function () { alert("저장하지 못했습니다."); });
  });
})();
