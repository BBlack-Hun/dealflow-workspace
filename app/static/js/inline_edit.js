// 표에서 칸을 눌러 바로 고친다.
//
// 투자컨설턴트 현황에서 먼저 쓰던 방식을 떼어냈다. 같은 조작을 화면마다
// 다시 만들면 동작이 조금씩 달라지고, 한 곳을 고쳐도 나머지가 그대로 남는다.
//
// 쓰는 법: 표에 data-inline-url 을 주고, 고칠 칸에 .cell 과 data-field 를 준다.
//   <table data-inline-url="/api/companies">        ← PATCH /api/companies/{id}
//     <tr data-id="3">
//       <td class="cell" data-field="name">샘플애그</td>
//       <td class="cell multi" data-field="memo">…</td>          여러 줄
//       <td class="cell" data-field="due_date" data-type="date">2026-08-26</td>
//       <td class="cell num" data-field="revenue_recent" data-type="number">1,200</td>
//       <td class="cell ellipsis" data-field="one_liner" data-type="long">긴 문장…</td>
//
// `data-type="long"` 은 **칸 위에 떠서** 고친다. 좁은 칸(한줄소개는 320px 말줄임)
// 안에서 한 줄짜리 입력으로 문장을 쓰면 앞뒤가 안 보인다 — 어디를 고치는지 모른 채
// 타이핑하게 된다. 뜬 창은 칸보다 넓고 줄바꿈되며, 표의 가로 스크롤에 잘리지 않게
// 화면 좌표로 띄운다.
//
// `.cell` 은 td 가 아니어도 된다. 한 칸에 여러 줄이 들어 있는 표(투자사 DB 처럼
// 메모 밑에 버튼이 붙어 있는 곳)에서는 고칠 줄에만 붙인다 — td 째로 바꾸면
// 같이 들어 있던 버튼이 사라진다.
//
// 칸을 벗어날 때만 저장한다. 글자마다 저장하면 요청이 쏟아진다.
// 저장 뒤 `inline-saved` 이벤트에 서버 응답(detail.data)이 실려 온다 —
// 다른 칸이 따라 바뀌는 표(기업의 '소개 가능')는 그걸 보고 고쳐 그린다.
(function (global) {
  "use strict";

  function attach(table) {
    var url = table.getAttribute("data-inline-url");
    if (!url) return;
    var editing = null;

    table.addEventListener("click", function (e) {
      var cell = e.target.closest(".cell[data-field]");
      if (!cell || cell === editing || !table.contains(cell)) return;
      start(cell);
    });

    function start(cell) {
      if (editing) return;
      editing = cell;

      var before = cell.textContent.trim();
      var type = cell.getAttribute("data-type") || "";
      if (type === "number") before = before.replace(/,/g, "");
      if (before === "-") before = "";        // 빈 칸을 '-' 로 그려 둔 표가 있다

      if (type === "long") { startLong(cell, before, type); return; }

      var multi = cell.classList.contains("multi");
      var input = document.createElement(multi ? "textarea" : "input");
      input.className = "cell-input";
      if (!multi) {
        input.type = type === "date" ? "date" : (type === "number" ? "number" : "text");
      }
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
        cell.textContent = type === "number" ? withCommas(after) : after;
        if (after !== before) save(cell, after, before, type);
      }
    }

    // 칸 위에 떠서 고친다 — 좁은 칸에 긴 문장을 넣을 때.
    function startLong(cell, before, type) {
      var pop = document.createElement("div");
      pop.className = "cell-pop";

      var area = document.createElement("textarea");
      area.className = "cell-pop-input";
      area.value = before;

      var hint = document.createElement("div");
      hint.className = "cell-pop-hint";
      hint.textContent = "⌘/Ctrl+Enter 저장 · Esc 취소";

      pop.appendChild(area);
      pop.appendChild(hint);
      document.body.appendChild(pop);
      place();
      grow();

      area.focus();
      area.setSelectionRange(area.value.length, area.value.length);

      var canceled = false;
      area.addEventListener("input", grow);
      area.addEventListener("blur", finish);
      area.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { canceled = true; area.blur(); }
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          area.blur();
        }
      });
      global.addEventListener("scroll", place, true);
      global.addEventListener("resize", place);

      function place() {
        var box = cell.getBoundingClientRect();
        pop.style.left = Math.max(8, Math.min(box.left, global.innerWidth - 468)) + "px";
        pop.style.width = Math.max(box.width, 440) + "px";
        // 아래로 자랄 자리가 없으면 위로 띄운다 — 표 맨 아랫줄에서 창이 잘리면
        // 고치는 중에 화면 밖으로 나간다.
        pop.style.top = "";
        pop.style.bottom = "";
        if (box.top + pop.offsetHeight + 12 > global.innerHeight) {
          pop.style.bottom = (global.innerHeight - box.bottom) + "px";
        } else {
          pop.style.top = box.top + "px";
        }
      }

      function grow() {
        area.style.height = "auto";
        area.style.height = Math.min(220, Math.max(56, area.scrollHeight)) + "px";
        place();
      }

      function finish() {
        if (editing !== cell) return;
        editing = null;
        global.removeEventListener("scroll", place, true);
        global.removeEventListener("resize", place);
        var after = canceled ? before : area.value.trim();
        if (pop.parentNode) pop.parentNode.removeChild(pop);
        cell.textContent = after;
        cell.title = after;
        if (after !== before) save(cell, after, before, type);
      }
    }

    function save(cell, value, before, type) {
      var row = cell.closest("tr");
      var id = row && row.getAttribute("data-id");
      if (!id) return;
      var body = {};
      // 숫자 칸은 빈 값이면 null 로 보낸다 — 0 과 '아직 안 적음'은 다르다.
      body[cell.getAttribute("data-field")] =
        type === "number" ? (value === "" ? null : Number(value)) : value;

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
          return r.json().catch(function () { return {}; }).then(function (data) {
            table.dispatchEvent(new CustomEvent("inline-saved",
              { detail: { row: row, cell: cell, value: value, data: data } }));
          });
        })
        .catch(function (err) {
          cell.classList.remove("saving");
          cell.classList.add("save-failed");
          // 저장 못 했으면 화면도 되돌린다 — 고쳐진 것처럼 보이면 안 된다.
          cell.textContent = type === "number" ? withCommas(before) : before;
          alert("저장하지 못했습니다." + (err.message ? "\n" + err.message : ""));
        });
    }
  }

  function withCommas(value) {
    if (value === "" || value === null || isNaN(Number(value))) return value;
    return Number(value).toLocaleString("ko-KR");
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
