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

  // ── 검색 · 필터 ────────────────────────────────────────────
  function apply() {
    var q = (search.value || "").trim().toLowerCase();
    var shown = 0;
    rows().forEach(function (tr) {
      var hit = !q || (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
      var pass = filter === ""
        || (filter === "managed" && tr.getAttribute("data-managed") === "1")
        || (filter === "dropped" && tr.getAttribute("data-dropped") === "1")
        || (filter === "nocontact" && tr.getAttribute("data-contacted") !== "1");
      var visible = hit && pass;
      tr.hidden = !visible;
      if (visible) shown += 1;
    });
    if (q || filter) {
      note.hidden = false;
      note.textContent = shown + " / " + rows().length + "곳 표시 중";
    } else {
      note.hidden = true;
    }
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
      })
      .catch(function () {
        cell.classList.remove("saving");
        cell.classList.add("save-failed");
        cell.textContent = before;      // 저장 못 했으면 화면도 되돌린다
        alert("저장하지 못했습니다. 잠시 후 다시 시도하세요.");
      });
  }

  // 관리/드랍 표시는 '기업 관리' 칸의 내용으로 정해진다 — 고치면 필터도 따라가야 한다.
  function refreshRowFlags(tr) {
    var mgmt = tr.querySelector('[data-field="management"]');
    var text = mgmt ? mgmt.textContent : "";
    tr.setAttribute("data-managed", text.indexOf("관리") >= 0 ? "1" : "0");
    tr.setAttribute("data-dropped", text.indexOf("드랍") >= 0 ? "1" : "0");
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
