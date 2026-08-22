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
//       <td><div class="cell clamp2" data-field="one_liner" data-type="long">긴 문장…</div></td>
//       <td class="cell" data-field="sector_major" data-type="pick">애그테크</td>
//
// `long` 과 `pick` 은 **칸 위에 떠서** 고친다. 좁은 칸 안에서 한 줄짜리 입력으로
// 고치면 앞뒤가 안 보인다 — 어디를 고치는지 모른 채 타이핑하게 된다. 뜬 창은
// 칸보다 넓고, 표의 가로 스크롤에 잘리지 않게 화면 좌표로 띄운다.
//
//   long — 여러 줄. 내용에 따라 높이가 자란다 (소개 문구 · 메모)
//   pick — 한 줄 + **이미 쓰고 있는 값 목록**. 분야·단계처럼 값이 몇 개로
//          정해져 있는 칸은 새로 타이핑하면 표기가 갈라진다("헬스케어" vs
//          "헬스 케어"). 목록은 같은 컬럼의 다른 행에서 그때그때 모은다 —
//          서버에 목록을 따로 두면 실제 값과 어긋난다.
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

      // 보이는 글자와 저장된 값이 다를 수 있다(단계는 표에 이름만 보인다).
      var before = cell.hasAttribute("data-value")
        ? cell.getAttribute("data-value") : cell.textContent.trim();
      var type = cell.getAttribute("data-type") || "";
      if (type === "number") before = before.replace(/,/g, "");
      if (before === "-") before = "";        // 빈 칸을 '-' 로 그려 둔 표가 있다

      if (type === "long") { startLong(cell, before, type); return; }
      if (type === "pick") { startPick(cell, before, type); return; }

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

    // ── 칸 위에 뜨는 편집창 ────────────────────────────────────────────
    //
    // 좁은 칸에 그대로 입력을 넣으면 고치는 내용이 안 보인다. long/pick 이
    // 이 창을 함께 쓴다 — 뜨고, 자리를 잡고, 벗어나면 저장하는 부분이 같다.
    function popover(cell, before, type, build) {
      var pop = document.createElement("div");
      pop.className = "cell-pop";
      document.body.appendChild(pop);

      var canceled = false;
      var done = false;

      var api = {
        pop: pop,
        cancel: function () { canceled = true; },
        // 목록에서 골랐을 때처럼 곧바로 끝내는 길
        commit: function (value) { finish(value); },
        place: place
      };
      var input = build(api);

      place();
      input.focus();
      if (input.setSelectionRange) {
        input.setSelectionRange(input.value.length, input.value.length);
      }
      input.addEventListener("blur", function () { finish(); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { canceled = true; input.blur(); }
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

      function finish(picked) {
        if (done) return;
        done = true;
        if (editing === cell) editing = null;
        global.removeEventListener("scroll", place, true);
        global.removeEventListener("resize", place);

        var after = canceled ? before
          : (picked !== undefined ? picked : input.value).trim();
        if (pop.parentNode) pop.parentNode.removeChild(pop);
        cell.textContent = after;
        cell.title = after;
        if (cell.hasAttribute("data-value")) cell.setAttribute("data-value", after);
        if (after !== before) save(cell, after, before, type);
      }
    }

    function startLong(cell, before, type) {
      popover(cell, before, type, function (api) {
        var area = document.createElement("textarea");
        area.className = "cell-pop-input";
        area.value = before;
        api.pop.appendChild(area);
        api.pop.appendChild(hintLine("⌘/Ctrl+Enter 저장 · Esc 취소"));

        area.addEventListener("input", grow);
        area.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            area.blur();
          }
        });
        grow();
        return area;

        function grow() {
          area.style.height = "auto";
          area.style.height = Math.min(220, Math.max(56, area.scrollHeight)) + "px";
          api.place();
        }
      });
    }

    // 값이 몇 개로 정해져 있는 칸(분야·단계). 새로 타이핑하면 표기가 갈라져서
    // 필터가 같은 뜻을 두 줄로 센다 — 쓰고 있는 값을 먼저 보여 준다.
    function startPick(cell, before, type) {
      popover(cell, before, type, function (api) {
        var input = document.createElement("input");
        input.type = "text";
        input.className = "cell-pop-input one-line";
        input.value = before;
        api.pop.appendChild(input);

        var used = knownValues(cell.getAttribute("data-field"));
        if (used.length) {
          var box = document.createElement("div");
          box.className = "cell-pop-choices";
          used.forEach(function (value) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "cell-pop-choice" + (value === before ? " on" : "");
            chip.textContent = value;
            // mousedown 이라야 input 의 blur 보다 먼저 잡힌다.
            chip.addEventListener("mousedown", function (e) {
              e.preventDefault();
              api.commit(value);
            });
            box.appendChild(chip);
          });
          api.pop.appendChild(box);
        }
        api.pop.appendChild(hintLine(
          used.length ? "골라 누르거나 새로 적습니다 · Enter 저장 · Esc 취소"
                      : "Enter 저장 · Esc 취소"));

        input.addEventListener("keydown", function (e) {
          if (e.key === "Enter") { e.preventDefault(); input.blur(); }
        });
        return input;
      });
    }

    // 같은 컬럼의 다른 행이 실제로 쓰고 있는 값. 서버에 목록을 따로 두면
    // 실제 값과 어긋난다 — 표에 있는 것이 곧 목록이다.
    function knownValues(field) {
      var seen = {};
      var out = [];
      table.querySelectorAll('[data-field="' + field + '"]').forEach(function (el) {
        var value = el.hasAttribute("data-value")
          ? el.getAttribute("data-value") : el.textContent.trim();
        if (!value || value === "-" || seen[value]) return;
        seen[value] = true;
        out.push(value);
      });
      return out.sort(function (a, b) { return a.localeCompare(b, "ko"); });
    }

    function hintLine(text) {
      var hint = document.createElement("div");
      hint.className = "cell-pop-hint";
      hint.textContent = text;
      return hint;
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
