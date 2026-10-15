// IR 기업 현황 메뉴의 `Series A 이상 기업` 탭 — 검색 · 머리글 필터 · 정렬 ·
// 줄 번호 · 저장 뒤처리 · 추가 · 삭제.
//
// 칸을 눌러 고치는 일은 공통 부품(`inline_edit.js`)이, 거르는 일은
// `filters.js` 가, 세우는 일은 `table_sort.js` 가 한다 — 이 파일은 그 셋을
// 이 표에 거는 것과, **서버만 아는 값**을 저장 뒤에 받아 적는 것만 한다.
// 옆 두 탭(`companies.js`)과 같은 짜임이다.
(function () {
  var table = document.getElementById("sa-table");
  if (!table) return;

  var search = document.getElementById("sa-search");
  var note = document.getElementById("sa-note");

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }

  // 검색창은 컬럼 필터 위에 AND 로 얹는다 — 둘이 각자 tr.hidden 을 만지면
  // 검색과 필터가 번갈아 서로를 지운다(`companies.js` 와 같은 이유).
  function textMatch(tr) {
    var q = (search.value || "").trim().toLowerCase();
    if (!q) return true;
    return (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
  }

  // 줄 번호는 **보이는 것 기준**이다 — 걸러낸 뒤 몇 건인지 세려고.
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

  function afterApply() {
    var total = rows().length;
    var shown = rows().filter(function (tr) { return !tr.hidden; }).length;
    renumber();
    note.hidden = shown === total;
    note.textContent = shown !== total ? shown + " / " + total + "건 표시 중" : "";
  }

  var filters = null;
  if (window.DealflowFilters) {
    filters = window.DealflowFilters.init({
      table: "#sa-table",
      unit: "건",
      extra: textMatch,
      onChange: afterApply
    });
  }

  function apply() {
    if (filters) { filters.apply(); return; }
    rows().forEach(function (tr) { tr.hidden = !textMatch(tr); });
    afterApply();
  }
  search.addEventListener("input", apply);

  // 머리글을 눌러 세운다. 세운 뒤 **번호를 다시 매긴다** — 이 표의 `NO` 는
  // 지금 서 있는 차례 그 자체라, 안 매기면 `3,5,1,…` 로 남는다.
  var sort = window.DealflowSort && window.DealflowSort.init({
    table: "#sa-table",
    onChange: renumber
  });

  // ── 저장 뒤처리 ──────────────────────────────────────────────────────
  //
  // 응답(`routers/series_a._result`)이 주는 값으로 **화면이 다시 만들 수 없는
  // 것**만 고쳐 적는다. 규칙을 여기 또 적으면 서버와 두 벌이 된다.
  //   · `투자라운드` — 칸에는 괄호 앞(`series_short`), 필터도 그 값.
  //   · `수신 일자` — 세울 값(`received_sort`). 날짜 모양도 서버가 맞춘다.
  //   · `IR 현황` 딱지 — 기업명을 고치면 맞는 기업이 달라진다.
  table.addEventListener("inline-saved", function (e) {
    var data = e.detail.data || {};
    var row = e.detail.row;
    var cell = e.detail.cell;
    if (!row || !("id" in data)) return;
    var field = cell && cell.getAttribute("data-field");

    if (field === "series") {
      cell.textContent = data.series_short || "";
      cell.setAttribute("data-value", data.series || "");
      if (cell.parentNode) cell.parentNode.title = data.series || "";
      row.setAttribute("data-f-series", data.series_short || "");
    }
    if (field === "received_at") {
      cell.textContent = data.received_at || "";
    }
    row.setAttribute("data-s-received_at", data.received_sort || "");

    var link = row.querySelector(".ir-link");
    if (link) {
      link.hidden = !data.ir_name;
      link.setAttribute("href", "/companies?q=" + encodeURIComponent(data.ir_name || ""));
    }
    // 세울 값을 다시 읽는다 — 위에서 고쳐 적은 뒤라 한 박자 뒤에.
    if (sort) window.setTimeout(sort.refresh, 0);
  });

  // ── 더하기 · 지우기 ───────────────────────────────────────────────────

  function send(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  // 기업명만 받아 **오늘 받은 딜**로 세운다(나머지는 표에서 눌러 고친다).
  document.getElementById("sa-add").addEventListener("click", function () {
    var name = (window.prompt("받은 딜의 기업명") || "").trim();
    if (!name) return;
    send("POST", "/api/series-a-companies", { name: name }).then(function (res) {
      if (!res.ok) { alert(res.d.detail || "추가하지 못했습니다"); return; }
      window.location.reload();
    }).catch(function () { alert("추가 요청 오류"); });
  });

  // 무엇을 지우는지 **이름으로** 묻는다 — "이 줄" 만으로는 어느 줄을 눌렀는지
  // 확신할 수 없다(옆 탭의 [삭제] 와 같은 이유).
  table.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-sa-delete");
    if (!btn) return;
    var tr = btn.closest("tr");
    var nameCell = tr.querySelector('[data-field="name"]');
    var name = nameCell ? nameCell.textContent.trim() : "";
    if (!window.confirm("'" + name + "' 줄을 지웁니다. 되돌릴 수 없습니다.")) return;
    send("DELETE", "/api/series-a-companies/" + tr.getAttribute("data-id"))
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "지우지 못했습니다"); return; }
        window.location.reload();
      }).catch(function () { alert("삭제 요청 오류"); });
  });

  apply();
})();
