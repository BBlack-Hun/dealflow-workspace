// 표에서 칸을 눌러 바로 고친다.
//
// 투자컨설턴트 현황에서 먼저 쓰던 방식을 떼어냈다. 같은 조작을 화면마다
// 다시 만들면 동작이 조금씩 달라지고, 한 곳을 고쳐도 나머지가 그대로 남는다.
//
// 쓰는 법: 표에 data-inline-url 을 주고, 고칠 칸에 .cell 과 data-field 를 준다.
//   <table data-inline-url="/api/companies">        ← PATCH /api/companies/{id}
//     <tr data-id="3">
//       <td class="cell" data-field="name">샘플애그</td>
//       <td class="cell multi" data-field="memo">…</td>       여러 줄
//       <td class="cell" data-field="due_date" data-type="date">2026-08-26</td>
//
// 칸을 벗어날 때만 저장한다. 글자마다 저장하면 요청이 쏟아진다.
(function (global) {
  "use strict";

  function attach(table) {
    var url = table.getAttribute("data-inline-url");
    if (!url) return;
    var editing = null;

    table.addEventListener("click", function (e) {
      var cell = e.target.closest("td.cell");
      if (!cell || cell === editing || !table.contains(cell)) return;
      start(cell);
    });

    function start(cell) {
      if (editing) return;
      editing = cell;

      var before = cell.textContent.trim();
      var type = cell.getAttribute("data-type") || "";
      var multi = cell.classList.contains("multi");
      var input = document.createElement(multi ? "textarea" : "input");
      input.className = "cell-input";
      if (!multi) input.type = type === "date" ? "date" : "text";
      input.value = before;
      if (multi) input.rows = Math.min(6, Math.max(2, before.split("\n").length + 1));

      cell.textContent = "";
      cell.appendChild(input);
      input.focus();
      if (input.setSelectionRange && !multi && type !== "date") {
        input.setSelectionRange(input.value.length, input.value.length);
      }

      input.addEventListener("blur", finish);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { input.value = before; input.blur(); }
        // 여러 줄 칸에서는 엔터가 줄바꿈이어야 한다. 저장은 Ctrl/Cmd+Enter.
        if (e.key === "Enter" && (!multi || e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          input.blur();
        }
      });

      function finish() {
        if (editing !== cell) return;
        editing = null;
        var after = input.value.trim();
        cell.textContent = after;
        if (after !== before) save(cell, after, before);
      }
    }

    function save(cell, value, before) {
      var row = cell.closest("tr");
      var id = row && row.getAttribute("data-id");
      if (!id) return;
      var body = {};
      body[cell.getAttribute("data-field")] = value;

      cell.classList.add("saving");
      fetch(url + "/" + id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      })
        .then(function (r) {
          cell.classList.remove("saving");
          if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || ""); });
          cell.classList.add("saved");
          setTimeout(function () { cell.classList.remove("saved"); }, 900);
          table.dispatchEvent(new CustomEvent("inline-saved",
            { detail: { row: row, cell: cell, value: value } }));
        })
        .catch(function (err) {
          cell.classList.remove("saving");
          cell.classList.add("save-failed");
          // 저장 못 했으면 화면도 되돌린다 — 고쳐진 것처럼 보이면 안 된다.
          cell.textContent = before;
          alert("저장하지 못했습니다." + (err.message ? "\n" + err.message : ""));
        });
    }
  }

  function init() {
    document.querySelectorAll("table[data-inline-url]").forEach(attach);
  }

  global.InlineEdit = { init: init, attach: attach };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
