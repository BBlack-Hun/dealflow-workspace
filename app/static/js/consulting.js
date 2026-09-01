// 투자컨설턴트 현황 — 시트처럼 칸을 눌러 바로 고친다.
//
// 원본이 구글시트라 쓰는 사람은 "칸을 눌러 고친다"에 익숙하다. 상세 패널을 여닫게
// 하면 56줄을 훑으며 고치는 일이 배로 느려지므로, 표에서 바로 고치게 한다.
// 칸을 벗어날 때만 저장한다(글자마다 저장하면 요청이 쏟아진다).
(function () {
  var table = document.getElementById("cs-table");
  if (!table) return;

  var search = document.getElementById("cs-search");
  var note = document.getElementById("cs-note");
  var filter = "";
  var filterName = "";   // 지금 눌린 칩의 이름. 무엇으로 걸렀는지 글자로 남긴다.

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }

  // 줄이 걸린 마디들. 갈래 표시는 `data-f-mgmt` **하나**이고 관리 중 · 드랍 칩도
  // 그것을 나눠 본다 — 예전에는 `data-managed`/`data-dropped` 를 따로 두어,
  // 같은 판단이 화면·서버·여기 세 곳에 적혀 있었다.
  function tagsOf(tr) {
    return (tr.getAttribute("data-f-mgmt") || "").split("|");
  }

  function hasTag(tr, tag) { return tagsOf(tr).indexOf(tag) >= 0; }

  // ── 검색 · 칩 · 컬럼 필터 ──────────────────────────────────
  //
  // 셋이 **AND** 로 묶여야 한다. 검색과 칩은 컬럼으로 표현할 수 없는 조건이라
  // filters.js 에 `extra` 로 넘긴다 — 둘이 따로 tr.hidden 을 쥐면 번갈아 서로를
  // 지운다(검색하면 컬럼 필터가 풀리고, 필터를 고르면 검색어가 풀린다).
  function passes(tr) {
    // `내용이 없습니다` 안내 행은 자료가 아니다 — 걸러서 감추면 왜 비었는지
    // 알려 줄 문구까지 같이 사라진다.
    if (!tr.getAttribute("data-id")) return true;
    var q = (search.value || "").trim().toLowerCase();
    var hit = !q || (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
    return hit && (filter === ""
      || (filter === "managed" && hasTag(tr, "관리 중"))
      || (filter === "dropped" && hasTag(tr, "드랍"))
      || (filter === "nocontact" && tr.getAttribute("data-contacted") !== "1"));
  }

  // 몇 곳이 남았는지. 걸러 놓고 건수를 안 보여 주면 다 본 것인지 알 수 없다.
  //
  // **무엇으로 걸렀는지도 적는다.** 건수만 두면 `연락 기록 없음`(어느 달이든
  // 기록이 없는 곳)과 위 KPI 의 `미완료 기업`(지난달만 본다)이 서로 다른
  // 숫자인데도 구별할 방법이 없다 — 실데이터로 7곳과 20곳이다.
  function showNote(state) {
    var all = rows();
    var shown = all.filter(function (tr) { return !tr.hidden; }).length;
    var picked = state ? Object.keys(state).length : 0;
    var q = (search.value || "").trim();
    note.hidden = !(q || filter || picked);
    if (!note.hidden) {
      note.textContent = shown + " / " + all.length + "곳 표시 중"
        + (filterName ? " · " + filterName : "")
        + (q ? " (검색: " + q + ")" : "");
    }
  }

  // ── 위 KPI ────────────────────────────────────────────────
  //
  // KPI 는 **거른 결과가 아니라 이 탭 전체**를 센다. `드랍` 만 보는 중이라고
  // `관리 중` 이 0 이 되면 안 된다 — 그건 필터가 아니라 표의 성질이다.
  // (deals.js 가 `data-match` 와 `hidden` 을 갈라 둔 것과 같은 이유: "조건에
  //  맞는가" 를 "보이는가" 로 읽으면 안 된다. 여기서는 `tr.hidden` 을 아예
  //  안 본다.)
  //
  // 세는 규칙은 서버(`services/consulting_status.py`)와 같아야 한다. 그래서
  // 줄에 적힌 값만 보고 세고, `기업 관리` 칸의 문장을 여기서 다시 읽지 않는다.
  function syncKpi() {
    var all = rows();
    var n = { total: all.length, managed: 0, dropped: 0, pending: 0 };
    all.forEach(function (tr) {
      if (hasTag(tr, "관리 중")) n.managed += 1;
      if (hasTag(tr, "드랍")) n.dropped += 1;
      if (tr.getAttribute("data-contacted-prev") !== "1") n.pending += 1;
    });
    Object.keys(n).forEach(function (key) {
      // 표식이 없는 숫자는 안 건드린다 — `미완료 기업` 은 지난달 칸이 표에
      // 서 있을 때만 표식이 붙는다(접혀 있으면 다시 셀 근거가 화면에 없다).
      var el = document.querySelector('[data-kpi="' + key + '"]');
      if (el) el.textContent = String(n[key]);
    });
  }

  var columnFilters = window.DealflowFilters && window.DealflowFilters.init({
    table: "#cs-table",
    extra: passes,
    onChange: showNote
  });

  // 표를 다시 거른다. **행 값을 다시 읽는 것부터** 한다 — 칸을 고치면 그 줄의
  // `data-f-*` 가 바뀌는데, filters.js 는 처음 한 번 읽은 값으로 목록을 만들기
  // 때문에 다시 읽지 않으면 화면에는 `관리 중` 이라고 적혀 있는데 필터에는
  // 여전히 `드랍` 으로 남는다.
  function apply() {
    // 위 숫자는 걸린 조건과 무관하다 — 어느 길로 가든 먼저 센다.
    // (`columnFilters` 가 있으면 아래에서 바로 빠져나가므로 여기 말고는
    //  둘 다 거치는 자리가 없다.)
    syncKpi();
    if (columnFilters) { columnFilters.refresh(); return; }   // refresh 안에서 적용까지 한다
    // 공통 부품을 못 실었을 때(스크립트 순서가 틀어졌다든지)라도 검색·칩은 살아 있어야 한다.
    rows().forEach(function (tr) { tr.hidden = !passes(tr); });
    showNote(null);
  }

  search.addEventListener("input", apply);
  // 칩은 **한 번에 하나**다. 세 칩이 한 갈래가 아니라서다 — 둘은 `기업 관리`
  // 이고 하나는 리마인드 기록이다. OR 로 묶으면 "관리 중이거나 연락 기록이
  // 없는 곳" 이라는 아무도 안 찾는 목록이 되고, AND 로 묶으면 관리 중 ∧ 드랍
  // 이 거의 늘 0줄이라 눌러도 빈 화면만 나온다. 같은 갈래를 여러 개 고르는
  // 일은 머리글 `기업 관리 ▾` 가 이미 한다(같은 컬럼 안에서는 OR).
  document.querySelectorAll("[data-cs-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("[data-cs-filter]").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      filter = btn.getAttribute("data-cs-filter");
      filterName = filter ? (btn.textContent || "").trim() : "";
      apply();
    });
  });

  // ── 칸에서 바로 고치기 ─────────────────────────────────────
  var editing = null;

  table.addEventListener("click", function (e) {
    var cell = e.target.closest("td.cell");
    if (!cell || cell === editing) return;
    startEdit(cell);
  });

  function startEdit(cell) {
    if (editing) finishEdit();
    editing = cell;
    var before = cell.textContent.trim();
    var multi = cell.classList.contains("multi");
    var input = document.createElement(multi ? "textarea" : "input");
    input.className = "cell-input";
    input.value = before;
    if (multi) input.rows = Math.min(6, Math.max(2, before.split("\n").length + 1));
    cell.textContent = "";
    cell.appendChild(input);
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);

    input.addEventListener("blur", finishEdit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = before; input.blur(); }
      // 여러 줄 칸에서는 엔터가 줄바꿈이어야 한다. 저장은 Ctrl/Cmd+Enter.
      if (e.key === "Enter" && (!multi || e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        input.blur();
      }
    });

    function finishEdit() {
      if (editing !== cell) return;
      editing = null;
      var after = input.value.trim();
      cell.textContent = after;
      if (after === before) return;
      save(cell, after, before);
    }
  }

  function save(cell, value, before) {
    var tr = cell.closest("tr");
    var id = parseInt(tr.getAttribute("data-id"), 10);
    var body = {};
    var noteId = cell.getAttribute("data-note");
    if (noteId) {
      var notes = {};
      notes[noteId] = value;
      body.notes = notes;
    } else {
      body[cell.getAttribute("data-field")] = value;
    }
    cell.classList.add("saving");
    fetch("/api/consulting/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) {
        cell.classList.remove("saving");
        if (!r.ok) throw new Error();
        cell.classList.add("saved");
        setTimeout(function () { cell.classList.remove("saved"); }, 900);
        refreshRowFlags(tr);
        // 플래그만 고치고 끝내면 **화면은 옛 조건 그대로**다. `드랍` 만 보는
        // 중에 한 곳을 `관리 중` 으로 바꾸면 이제 드랍이 아닌데도 목록에
        // 남아 있고, 위의 표시 건수도 안 맞는다 — 새로고침해야 사라진다.
        // 다른 화면(투자사·기업·딜 소싱)은 저장하면 필터가 곧바로 다시
        // 걸리므로, 여기만 다르게 두면 같은 조작이 화면마다 달리 동작한다.
        apply();
      })
      .catch(function () {
        cell.classList.remove("saving");
        cell.classList.add("save-failed");
        cell.textContent = before;      // 저장 못 했으면 화면도 되돌린다
        alert("저장하지 못했습니다. 잠시 후 다시 시도하세요.");
      });
  }

  // 계약 탭인가. `계약여부` 칸은 값이 `무료`/`유료` 라 추리지 않고 그대로 건다.
  var contractSheet = table.getAttribute("data-contract-sheet") === "1";

  // `기업 관리` 칸이 어느 갈래인가. **브라우저 쪽 규칙은 이 함수 하나뿐이다** —
  // 칩도 KPI 도 머리글 필터도 여기서 나온 태그를 나눠 볼 뿐, 칸의 문장을 다시
  // 읽지 않는다.
  //
  // 서버의 `services/consulting_status.py` 와 **같은 말을 같은 순서로** 봐야
  // 한다. 언어가 둘이라 한 벌씩은 어쩔 수 없지만, 어긋나면 고친 직후와
  // 새로고침 뒤에 같은 줄이 서로 다른 값으로 걸린다.
  // (같은 마디가 양쪽에 있는지는 `tests/test_filter_columns.py` 가 지킨다.)
  function managementTags(text) {
    // 계약 탭의 `계약여부` 는 이미 추려진 값이다. 아래 규칙을 태우면 `무료`·
    // `유료` 가 전부 `기타 메모` 로 묶여 고를 것이 없어진다.
    if (contractSheet) return text.trim();
    var tags = [];
    if (text.indexOf("관리") >= 0) tags.push("관리 중");
    if (text.indexOf("드랍") >= 0) tags.push("드랍");
    if (text.indexOf("백업팀") >= 0) tags.push("백업팀 전환");
    if (!tags.length && text.trim()) tags.push("기타 메모");
    return tags.join("|");
  }

  // 줄에 붙는 표시는 전부 칸의 내용에서 나온다 — 고치면 다 같이 따라가야 한다.
  // 칩도 KPI 도 머리글 필터도 **여기서 적은 값만** 본다.
  function refreshRowFlags(tr) {
    var mgmt = tr.querySelector('[data-field="management"]');
    tr.setAttribute("data-f-mgmt", managementTags(mgmt ? mgmt.textContent : ""));
    var region = tr.querySelector('[data-field="region"]');
    tr.setAttribute("data-f-region", region ? region.textContent.trim() : "");
    // **적힌 것이 있는가**는 앞뒤 공백을 뗀 뒤에 본다. 서버도 같은 규칙이다
    // (`consulting_status.contacted`) — 예전에는 서버가 공백만 든 칸을 기록으로
    // 세서, 그런 줄이 아무 칸이나 고치는 순간 `연락 기록 없음` 으로 넘어갔다.
    function filled(td) { return td.textContent.trim().length > 0; }
    // **접어 둔 달의 기록도 기록이다.** 여기서 볼 수 있는 것은 펴 둔 달의 칸뿐이라,
    // 이 줄이 없으면 접힌 달에만 기록이 있는 줄이 칸을 고치는 순간 `연락 기록 없음`
    // 으로 뒤집힌다 — 화면에 안 보이는 사실이라 고친 사람은 이유를 알 수 없다.
    // 접힌 달의 사실은 서버가 `data-contacted-folded` 로 실어 준다.
    var hasNote = tr.getAttribute("data-contacted-folded") === "1"
      || Array.prototype.some.call(tr.querySelectorAll("[data-note]"), filled);
    tr.setAttribute("data-contacted", hasNote ? "1" : "0");
    // 위 KPI 의 `미완료 기업` 은 **지난달 칸만** 센다. 어느 칸이 지난달인지는
    // 서버가 `data-prev-note` 로 찍어 준다 — 열 이름이 자유 문장이라
    // (`8월 마지막주 리마인드 톡 or TEL`) 여기서 달을 읽게 두면 규칙이 또
    // 한 벌 생긴다. 지난달 열이 접혀 있으면 그 표가 아예 안 붙고, 그때는
    // KPI 에도 표식이 없어 이 값이 쓰이지 않는다.
    var prev = tr.querySelectorAll("[data-prev-note]");
    if (prev.length) {
      tr.setAttribute("data-contacted-prev",
                      Array.prototype.some.call(prev, filled) ? "1" : "0");
    }
    var parts = [];
    Array.prototype.forEach.call(tr.querySelectorAll("td.cell"), function (td) {
      parts.push(td.textContent);
    });
    tr.setAttribute("data-search", parts.join(" ").toLowerCase());
  }

  // ── 추가 · 삭제 ────────────────────────────────────────────
  var addBtn = document.getElementById("cs-add");
  addBtn.addEventListener("click", function () {
    // 어느 탭에 들어가는지 물어볼 때 미리 알려 준다 — 딜 소싱의 `[○○에 추가]`와 같다.
    var sheet = (addBtn.getAttribute("data-sheet") || "").trim();
    var name = prompt("기업명을 입력하세요" + (sheet ? " (" + sheet + ")" : ""));
    if (!name || !name.trim()) return;
    // **지금 보고 있는 탭을 함께 보낸다.** 안 보내면 서버가 첫 탭에 넣어서,
    // 다른 탭에서 누른 사람에게는 추가가 안 된 것처럼 보였다(줄은 만들어졌지만
    // 보고 있는 탭에 없다). 서버는 `sheet` 가 없으면 예전처럼 첫 탭에 넣으므로,
    // 빈 값이면 아예 싣지 않아 옛 동작을 그대로 둔다.
    var body = { company_name: name.trim() };
    if (sheet) body.sheet = sheet;
    fetch("/api/consulting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "추가 실패"); return; }
        window.location.reload();
      });
  });

  table.addEventListener("click", function (e) {
    if (!e.target.classList.contains("js-cs-del")) return;
    var tr = e.target.closest("tr");
    var name = tr.querySelector('[data-field="company_name"]').textContent.trim();
    if (!confirm("'" + name + "' 줄을 삭제할까요?")) return;
    fetch("/api/consulting/" + tr.getAttribute("data-id"), { method: "DELETE" })
      .then(function (r) {
        if (!r.ok) { alert("삭제 실패"); return; }
        tr.remove();
        apply();
      });
  });

  var importBtn = document.getElementById("cs-import-btn");
  var importPanel = document.getElementById("cs-import");
  importBtn.addEventListener("click", function () { importPanel.hidden = !importPanel.hidden; });
  document.getElementById("cs-import-close").addEventListener("click", function () {
    importPanel.hidden = true;
  });
})();
