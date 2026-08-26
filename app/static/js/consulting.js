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

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }

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
      || (filter === "managed" && tr.getAttribute("data-managed") === "1")
      || (filter === "dropped" && tr.getAttribute("data-dropped") === "1")
      || (filter === "nocontact" && tr.getAttribute("data-contacted") !== "1"));
  }

  // 몇 곳이 남았는지. 걸러 놓고 건수를 안 보여 주면 다 본 것인지 알 수 없다.
  function showNote(state) {
    var all = rows();
    var shown = all.filter(function (tr) { return !tr.hidden; }).length;
    var picked = state ? Object.keys(state).length : 0;
    var q = (search.value || "").trim();
    note.hidden = !(q || filter || picked);
    if (!note.hidden) note.textContent = shown + " / " + all.length + "곳 표시 중";
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
    if (columnFilters) { columnFilters.refresh(); return; }   // refresh 안에서 적용까지 한다
    // 공통 부품을 못 실었을 때(스크립트 순서가 틀어졌다든지)라도 검색·칩은 살아 있어야 한다.
    rows().forEach(function (tr) { tr.hidden = !passes(tr); });
    showNote(null);
  }

  search.addEventListener("input", apply);
  document.querySelectorAll("[data-cs-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("[data-cs-filter]").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      filter = btn.getAttribute("data-cs-filter");
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

  // 머리글 필터가 보는 값. 서버의 `management_tags`(routers/consulting.py)와
  // **같은 말을 같은 순서로** 봐야 한다 — 규칙이 어긋나면 고친 직후와 새로고침
  // 뒤에 같은 줄이 서로 다른 값으로 걸린다.
  function managementTags(text) {
    var tags = [];
    if (text.indexOf("관리") >= 0) tags.push("관리 중");
    if (text.indexOf("드랍") >= 0) tags.push("드랍");
    if (text.indexOf("백업팀") >= 0) tags.push("백업팀 전환");
    if (!tags.length && text.trim()) tags.push("기타 메모");
    return tags.join("|");
  }

  // 관리/드랍 표시와 머리글 필터 값은 '기업 관리'·'지역' 칸의 내용으로 정해진다 —
  // 고치면 둘 다 따라가야 한다.
  function refreshRowFlags(tr) {
    var mgmt = tr.querySelector('[data-field="management"]');
    var text = mgmt ? mgmt.textContent : "";
    tr.setAttribute("data-managed", text.indexOf("관리") >= 0 ? "1" : "0");
    tr.setAttribute("data-dropped", text.indexOf("드랍") >= 0 ? "1" : "0");
    tr.setAttribute("data-f-mgmt", managementTags(text));
    var region = tr.querySelector('[data-field="region"]');
    tr.setAttribute("data-f-region", region ? region.textContent.trim() : "");
    var hasNote = Array.prototype.some.call(
      tr.querySelectorAll("[data-note]"),
      function (td) { return td.textContent.trim().length > 0; });
    tr.setAttribute("data-contacted", hasNote ? "1" : "0");
    var parts = [];
    Array.prototype.forEach.call(tr.querySelectorAll("td.cell"), function (td) {
      parts.push(td.textContent);
    });
    tr.setAttribute("data-search", parts.join(" ").toLowerCase());
  }

  // ── 추가 · 삭제 ────────────────────────────────────────────
  document.getElementById("cs-add").addEventListener("click", function () {
    var name = prompt("기업명을 입력하세요");
    if (!name || !name.trim()) return;
    fetch("/api/consulting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_name: name.trim() })
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
