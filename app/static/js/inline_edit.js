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
//   email — 한 줄 + **`@` 뒤 도메인 후보**. 주소 자체는 줄마다 달라 고를 것이
//          못 되지만 도메인은 겹친다(`services/email_domains.py` 의 재 둔 값).
//          `pick` 과 달리 목록은 이 표에서 모으지 않는다 — 메일 칸이 표에 안
//          선 명단이 있어서, 표에서 모으면 그 명단에서만 후보가 없어진다.
//
// `.cell` 은 td 가 아니어도 된다. 한 칸에 여러 줄이 들어 있는 표(투자사 관리 현황 처럼
// 메모 밑에 버튼이 붙어 있는 곳)에서는 고칠 줄에만 붙인다 — td 째로 바꾸면
// 같이 들어 있던 버튼이 사라진다.
//
// 칸을 벗어날 때만 저장한다. 글자마다 저장하면 요청이 쏟아진다.
// 칸 안에서 고치는 것은 입력칸을 벗어날 때(blur), **떠서 고치는 창(long·pick)은
// 창 바깥을 눌렀을 때** 끝난다 — 창 안이면 여백이든 보기 목록이든 안 닫힌다.
// 저장 뒤 `inline-saved` 이벤트에 서버 응답(detail.data)이 실려 온다 —
// 다른 칸이 따라 바뀌는 표(기업의 '소개 가능')는 그걸 보고 고쳐 그린다.
//
// ── 키보드로 칸·줄 사이를 넘어간다 ──────────────────────────────────────
//
// 담당 줄이 여든인 사람이 같은 칸을 여든 번 고친다. 지금까지는 칸 하나를
// 끝낼 때마다 초점이 문서 맨 위(BODY)로 빠져서, **다음 칸을 마우스로 다시
// 조준**해야 했다 — 여든 줄이면 백예순 번이다. 값을 적는 일이 아니라 겨냥하는
// 일이 대부분이었다.
//
//   Tab · Shift+Tab   옆 칸. **줄의 끝에서는 막지 않는다** — 브라우저가 차례대로
//                     그 줄의 [수정] 단추로, 그다음 줄로 넘긴다. 여기서 가로채
//                     다음 줄로 건너뛰면 표 안에서 그 단추에 닿을 길이 없어진다.
//   Enter             고치기 시작 / 고치던 것을 저장하고 **아래 줄 같은 칸**으로.
//                     시트에서 세로로 훑어 내려가며 적던 그 손놀림이다.
//   방향키            고치지 않는 동안의 이동. 위·아래는 같은 칸, 좌·우는 옆 칸.
//   pick 창           ↑↓ 로 보기를 고르고 Enter 로 확정. 보기에는 숫자가 붙어
//                     있어 `3` 한 번으로도 고른다(아래 `startPick`).
//
// **거른 표에서는 보이는 줄만 지난다**(`tr.hidden` 을 건너뛴다). 안 그러면
// 걸러 놓고 안 보이는 줄을 고치게 된다 — 고친 사람은 무엇을 고쳤는지 모른다.
//
// **초점이 간 칸이 안 보이면 따라 민다**(`reveal`). 이 표들은 화면보다
// 1,900px 넘게 넓고 첫 열·머리행이 고정이라, 그냥 두면 초점이 고정된 칸
// **밑에** 숨거나 화면 밖에 선다 — 그러면 사람이 길을 잃는다.
(function (global) {
  "use strict";

  function attach(table) {
    var url = table.getAttribute("data-inline-url");
    if (!url) return;
    var editing = null;

    table.addEventListener("click", function (e) {
      var cell = e.target.closest(".cell[data-field]");
      // 칸 옆에 세운 안내 딱지(`.cell-hint`)를 눌러도 그 칸이 열려야 한다.
      // 빈 칸은 글자가 없어 누를 자리가 한 줄뿐이라, 옆의 딱지가 사실상
      // 그 칸의 손잡이다 — 눌러도 아무 일이 없으면 고장으로 보인다.
      if (!cell) {
        var hint = e.target.closest(".cell-hint");
        if (hint && hint.parentNode) {
          cell = hint.parentNode.querySelector(".cell[data-field]");
        }
      }
      if (!cell || cell === editing || !table.contains(cell)) return;
      try {
        start(cell);
      } catch (err) {
        // 여는 도중에 뭐라도 터지면 `editing` 을 놓아 준다. 물린 채로 두면
        // 그 칸에서 빠져나올 수도, 다른 칸을 누를 수도 없어 **표 전체가
        // 먹통**이 된다 — 브라우저 API 하나 때문에 실제로 그랬다.
        editing = null;
        throw err;
      }
    });

    // ── 키보드 길 ──────────────────────────────────────────────────────
    //
    // **칸이 초점을 받을 수 있어야 키가 닿는다.** 표에 그려져 있는 칸에 한 번만
    // 달아 둔다 — 이 표들은 서버가 다 그려 보내고 줄이 늘거나 줄지 않는다.
    // 이미 적혀 있으면 그대로 둔다(화면이 제 뜻으로 정해 둔 차례를 덮지 않게).
    table.querySelectorAll(".cell[data-field]").forEach(function (cell) {
      if (!cell.hasAttribute("tabindex")) cell.setAttribute("tabindex", "0");
    });

    // 그 줄에서 고칠 수 있는 칸들, **그려진 차례 그대로**.
    function cellsIn(row) {
      return Array.prototype.slice.call(row.querySelectorAll(".cell[data-field]"));
    }

    // **보이는 줄만.** 거른 표에서 `tr.hidden` 을 지나가면, 걸러 놓고 안 보이는
    // 줄을 고치게 된다(`filters.js` 가 줄을 그렇게 감춘다).
    // 머리행은 고칠 칸이 없어서 저절로 빠진다 — `thead` 를 이름으로 짚지 않는
    // 이유는 이 편집기를 쓰는 표 중에 머리를 따로 안 감싼 것이 있어서다.
    function liveRows() {
      return Array.prototype.filter.call(table.querySelectorAll("tr"),
        function (tr) { return !tr.hidden && cellsIn(tr).length > 0; });
    }

    function sideways(cell, step) {
      var row = cell.closest("tr");
      if (!row) return null;
      var list = cellsIn(row);
      return list[list.indexOf(cell) + step] || null;
    }

    // 위·아래는 **같은 칸**으로 간다. 자리 번호가 아니라 `data-field` 로 찾는다 —
    // 줄마다 칸 수가 다른 표(감춘 줄에만 서는 체크상자)에서 번호로 세면 한 칸씩
    // 밀린 자리에 내려앉는다. 이름이 없으면 그때만 번호로 물러난다.
    function downward(cell, step) {
      var row = cell.closest("tr");
      var rows = liveRows();
      var at = rows.indexOf(row);
      if (at < 0) return null;          // 고치는 사이에 걸러져 감춰진 줄
      var next = rows[at + step];
      if (!next) return null;
      var field = cell.getAttribute("data-field");
      var list = cellsIn(next);
      for (var i = 0; i < list.length; i += 1) {
        if (list[i].getAttribute("data-field") === field) return list[i];
      }
      return list[cellsIn(row).indexOf(cell)] || null;
    }

    // 옮겨 간 칸에 초점을 주고, 안 보이면 따라 민다.
    function focusCell(cell) {
      if (!cell) return;
      // `preventScroll` — **브라우저가 먼저 밀지 못하게 한다.** 브라우저의
      // '보이게 하기' 는 붙어 선 칸(`.stick`)과 머리행을 모르기 때문에 초점을
      // 그 밑으로 밀어 넣는다. 우리가 밀기 전에 그쪽이 움직이면 화면이 두 번
      // 튄다. 모르는 브라우저는 이 값을 무시하고 예전처럼 민다 — 그래도 바로
      // 뒤의 `reveal` 이 제자리로 잡는다.
      try { cell.focus({ preventScroll: true }); } catch (err) { /* 초점은 곁가지다 */ }
      reveal(cell);
    }

    // 고치던 것을 끝낸 뒤 **아래 줄 같은 칸**으로. 마지막 줄이면 제자리에
    // 남는다 — 초점을 놓아 버리면 다음 Tab 이 문서 맨 위로 간다(고치기 전과
    // 같은 상태다).
    function stepDown(cell) {
      focusCell(downward(cell, 1) || cell);
    }

    table.addEventListener("keydown", function (e) {
      var cell = e.target && e.target.closest && e.target.closest(".cell[data-field]");
      // **칸 안의 입력칸에서 친 키는 그 입력칸이 맡는다.** 여기서 같이 받으면
      // 글자를 치는 동안 초점이 옆 칸으로 달아난다.
      if (!cell || cell !== e.target || !table.contains(cell)) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;

      // F2 는 시트에서 '이 칸 고치기'다. Enter 와 같이 둔다 — 쓰던 손이 있다.
      if (e.key === "Enter" || e.key === "F2") {
        e.preventDefault();
        start(cell);
        return;
      }
      if (e.key === "Tab") {
        var side = sideways(cell, e.shiftKey ? -1 : 1);
        // 줄의 끝에서는 **브라우저에 맡긴다** — 그래야 [수정] 단추와 다음 줄로
        // 차례가 이어진다(위 머리말 참고).
        if (!side) return;
        e.preventDefault();
        focusCell(side);
        return;
      }
      var step = ARROWS[e.key];
      if (!step) return;
      var to = step[0] ? downward(cell, step[0]) : sideways(cell, step[1]);
      if (!to) return;        // 끝 줄·끝 칸에서는 막지 않는다(표가 밀리게 둔다)
      e.preventDefault();
      focusCell(to);
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
      if (type === "email") { startEmail(cell, before, type); return; }

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

      // **빠져나갈 길을 먼저 만든다.** 아래에서 뭐라도 던지면 blur·Escape 가
      // 안 붙고, editing 이 이 칸에 물린 채 남아 표 전체가 먹통이 된다 —
      // 실제로 그랬다(아래 setSelectionRange 참고).
      input.addEventListener("blur", finish);
      input.addEventListener("keydown", function (e) {
      // **한글을 조합하는 중에는 비켜선다.** 한글 입력기는 글자를 만드는
      // 동안 Enter·방향키를 제가 쓴다(조합을 굳히고, 후보를 고른다). 여기서
      // 가로채면 `ㄱㅏ` 를 굳히려고 친 Enter 가 **칸을 저장하고 아래 줄로**
      // 가 버려서, 만들던 글자가 통째로 사라진다 — 이 앱은 적는 말이 죄다
      // 한글이라 그 자리가 곧 일상이다. `keyCode 229` 는 옛 브라우저의 같은 말.
      if (e.isComposing || e.keyCode === 229) return;
        // 끝낸 뒤에 **초점을 그 칸에 돌려준다.** 안 돌려주면 초점이 문서 맨
        // 위(BODY)로 빠져서, 다음 칸을 마우스로 다시 조준해야 한다 — 이 고침이
        // 없애려는 바로 그것이다.
        if (e.key === "Escape") {
          input.value = before;
          input.blur();
          focusCell(cell);
          return;
        }
        // 여러 줄 칸에서는 엔터가 줄바꿈이어야 한다. 저장은 Ctrl/Cmd+Enter.
        if (e.key === "Enter" && (!multi || e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          input.blur();                 // 여기서 finish() 가 돌아 저장까지 간다
          stepDown(cell);
          return;
        }
        // Tab 은 **저장하고 옆 칸**이다. 옮겨 간 칸을 바로 열지는 않는다 —
        // 지나가는 길에 값이 열려 버리면, 훑어보려던 칸이 저장 대상이 된다.
        if (e.key === "Tab") {
          // **여기서는 줄의 끝에서도 막는다.** 안 막으면 브라우저가 초점을
          // 옮기는 사이에 `blur` 가 이 입력칸을 지워 버려서, 초점이 어디로
          // 갈지가 브라우저 사정이 된다. 저장하고 그 칸에 돌려놓으면, 다음
          // Tab 은 칸에서 눌리는 것이라 예전처럼 [수정] 단추로 이어진다.
          e.preventDefault();
          input.blur();
          focusCell(sideways(cell, e.shiftKey ? -1 : 1) || cell);
        }
      });

      try {
        input.focus();
        putCaretAtEnd(input, multi, type);
      } catch (err) {
        // 여기서 실패해도 고치는 것 자체는 되어야 한다. 커서 위치는 곁가지다.
      }

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
        // 지금 적힌 그대로 끝내는 길(Enter · ⌘/Ctrl+Enter). 예전에는 이 자리에서
        // `input.blur()` 를 불러 blur 처리에 얹혀 갔는데, 이제 blur 로 닫지
        // 않으므로 끝내는 말을 직접 해야 한다.
        close: function () { finish(); },
        place: place
      };
      var input = build(api);

      // ── 언제 닫히는가 ────────────────────────────────────────────────
      //
      // **창 바깥을 눌렀을 때만 닫는다.** 예전에는 입력칸의 `blur` 하나에만
      // 걸어 두어서, 창의 여백이나 보기 목록의 스크롤바(`.cell-pop-choices` 는
      // 132px 에서 넘치면 스크롤된다)를 눌러도 focus 가 빠지면서 **창이
      // 저장되며 닫혔다** — 고를 것을 보려고 목록을 내리다 창이 사라진다.
      //
      // 바깥 판정은 `pop.contains` 하나로 한다. 그래서 칸 옆의 안내 딱지
      // (`.cell-hint`)는 **바깥이다** — 그것은 다른 칸의 손잡이라, 누르면 지금
      // 창이 끝나고 그 칸이 열려야 한다(누르는 순서가 pointerdown → click 이라
      // 이 창이 먼저 닫히고 그 다음에 새 칸이 열린다).
      //
      // 잡는 자리를 문서로 올린 값: 여백을 눌러 focus 가 창 밖으로 빠진 뒤에도
      // Escape 로 취소할 수 있다.
      function onDown(e) {
        if (pop.contains(e.target)) return;
        finish();
      }
      function onKey(e) {
        if (e.key !== "Escape") return;
        canceled = true;
        finish();
        // 취소해도 **초점은 표에 남는다.** 안 돌려주면 Escape 한 번에 초점이
        // 문서 맨 위로 빠져, 다음 칸을 다시 마우스로 찾아야 한다.
        focusCell(cell);
      }
      // ── Tab — **저장하고 옆 칸** ─────────────────────────────────────
      //
      // 창 하나에 걸어 두고 long·pick·email 이 함께 쓴다. 안 걸어 두면 Tab 이
      // 브라우저 기본대로 초점만 빼 가는데, **이 창은 바깥을 '눌렀을' 때만
      // 닫히므로**(#152) 초점이 빠져도 안 닫힌다 — 창은 떠 있는데 키는 딴 데서
      // 먹는 상태가 된다. 칸이 초점을 받게 된 뒤로는 그 자리가 늘 열려 있다.
      //
      // 줄의 끝에서도 막는다(칸 안에서 고칠 때와 같은 이유). 저장하고 그 칸에
      // 돌려놓으면 다음 Tab 은 칸에서 눌리는 것이라 [수정] 단추로 이어진다.
      function onTab(e) {
        if (e.key !== "Tab" || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        var side = sideways(cell, e.shiftKey ? -1 : 1);
        finish();
        focusCell(side || cell);
      }
      pop.addEventListener("keydown", onTab);

      document.addEventListener("pointerdown", onDown, true);
      document.addEventListener("keydown", onKey);

      place();
      try {
        input.focus();
        // **값이 정해진 칸은 글자를 통째로 골라 둔다**(`data-select-all`).
        // 커서를 끝에 두면 치는 글자가 옛 값 **뒤에 이어 붙어서**, `미확인` 이
        // 든 칸에 적으면 `미확인투자유치 진행 중` 이 저장된다 — 보기가 정해진
        // 칸에서 그런 값이 하나 생기면 필터가 그 줄만 따로 센다.
        // 자유롭게 적는 칸(long·email)은 그대로 끝에 둔다 — 그쪽은 이어 적는
        // 것이 하려던 일이다(메모에 한 줄 덧붙이기 · 주소 뒤 도메인 고치기).
        if (input.getAttribute("data-select-all") && input.select) input.select();
        else putCaretAtEnd(input, input.tagName === "TEXTAREA", "");
      } catch (err) {
        /* 커서 위치는 곁가지다 */
      }
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
        document.removeEventListener("pointerdown", onDown, true);
        document.removeEventListener("keydown", onKey);
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
          if (e.isComposing || e.keyCode === 229) return;   // 조합 중에는 비켜선다
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            api.close();
            stepDown(cell);
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
        // 열면 글자가 통째로 골라져 있다 — 치는 순간 옛 값이 밀려난다.
        // 왜 이 칸만 그런지는 `popover` 의 초점 잡는 자리에 적어 두었다.
        input.setAttribute("data-select-all", "1");
        api.pop.appendChild(input);

        // 정해진 보기가 있는 칸은 그것을 먼저 세운다. 값이 하나도 없는
        // 컬럼(관심도처럼 이제 채우기 시작하는 칸)은 다른 행에서 모을 것이
        // 없어서, 목록 없이 빈 칸에 타이핑하게 된다 — 그러면 사람마다
        // "높음" · "상" · "high" 로 갈린다.
        var fixed = (cell.getAttribute("data-choices") || "")
          .split(",").map(function (v) { return v.trim(); })
          .filter(function (v) { return v; });
        var used = fixed.slice();
        knownValues(cell.getAttribute("data-field")).forEach(function (v) {
          if (used.indexOf(v) === -1) used.push(v);
        });

        // 서버가 골라 준 후보(`data-suggest`)를 맨 앞으로.
        var picked = suggestedFirst(used, cell.getAttribute("data-suggest"));
        var suggested = picked.suggested;
        used = picked.order;

        // 키로 고르는 자리. `at` 은 지금 **키가 짚고 있는** 보기다 —
        // `-1` 이면 아무것도 안 짚은 것이고, 그때 Enter 는 적힌 그대로 저장한다.
        var chips = [];
        var at = -1;

        if (used.length) {
          var box = document.createElement("div");
          box.className = "cell-pop-choices";
          used.forEach(function (value, i) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "cell-pop-choice" + (value === before ? " on" : "")
              + (suggested.indexOf(value) !== -1 ? " suggested" : "");
            chip.textContent = value;
            // **번호는 글자가 아니라 속성이다**(`data-key`). CSS 가 앞에 그려
            // 준다 — 글자에 섞어 넣으면 눌러 저장되는 값에 번호가 딸려 간다.
            // 아홉까지만 붙인다. 두 자리 수를 치는 동안에는 앞자리가 먼저
            // 저장돼 버려서, 번호가 오히려 함정이 된다.
            if (i < 9) chip.setAttribute("data-key", String(i + 1));
            if (suggested.indexOf(value) !== -1) {
              chip.title = "한줄 소개를 보고 고른 후보입니다 — 맞는지 보고 고르세요";
            }
            // mousedown 이라야 input 의 blur 보다 먼저 잡힌다.
            chip.addEventListener("mousedown", function (e) {
              e.preventDefault();
              api.commit(value);
            });
            chips.push(chip);
            box.appendChild(chip);
          });
          api.pop.appendChild(box);
        }
        api.pop.appendChild(hintLine(
          suggested.length
            ? "앞 " + suggested.length + "개는 한줄 소개를 보고 고른 후보입니다 "
              + "— 맞는 것이 없으면 아래에서 고르세요 · ↑↓ 또는 숫자키로 고르기 "
              + "· Enter 저장 · Esc 취소"
            : used.length ? "↑↓ 또는 숫자키로 고릅니다(새로 적어도 됩니다) "
                            + "· Enter 저장 · Esc 취소"
                          : "Enter 저장 · Esc 취소"));

        // 지금 값에서 시작한다. 목록에 없는 값(자유롭게 적어 둔 것)이면 아무
        // 것도 안 짚는다 — 그래야 **아무 키도 안 누르고 Enter** 를 쳤을 때
        // 값이 그대로 남는다(고치려던 것이 아니라 열어 본 것일 수 있다).
        mark(used.indexOf(before));

        function mark(next) {
          at = next;
          chips.forEach(function (chip, i) {
            chip.classList.toggle("key-on", i === at);
          });
          // 보기 목록은 132px 에서 넘치면 스크롤된다 — 짚은 것이 그 밖에
          // 있으면 무엇을 고르는 중인지 안 보인다.
          if (at >= 0 && chips[at] && chips[at].scrollIntoView) {
            try { chips[at].scrollIntoView({ block: "nearest" }); } catch (err) { }
          }
        }

        function move(step) {
          if (!chips.length) return;
          if (at < 0) mark(step > 0 ? 0 : chips.length - 1);
          else mark(Math.min(chips.length - 1, Math.max(0, at + step)));
        }

        // 고르고 **아래 줄 같은 칸**으로. 여든 줄을 같은 칸으로 훑어 내려가는
        // 것이 이 표에서 하는 일이다.
        function take(value) {
          var to = downward(cell, 1) || cell;
          api.commit(value);
          focusCell(to);
        }

        // **직접 적기 시작하면 숫자 단축키를 거둔다.** 값에 숫자가 들어가는
        // 칸이 있어서(`2026-09`), 치는 숫자가 보기를 고르면 적을 수가 없다.
        // 번호 표시도 같이 지운다 — 안 되는 길이 보이면 그게 더 나쁘다.
        var typed = false;
        input.addEventListener("input", function () {
          if (typed) return;
          typed = true;
          chips.forEach(function (chip) { chip.removeAttribute("data-key"); });
          mark(-1);
        });

        input.addEventListener("keydown", function (e) {
          // 조합 중에는 비켜선다 — ↑↓ 는 입력기의 후보 고르기이고, Enter 는
          // 만들던 글자를 굳히는 키다(위 `start` 의 같은 자리 참고).
          if (e.isComposing || e.keyCode === 229) return;
          if (e.key === "ArrowDown") { e.preventDefault(); move(1); return; }
          if (e.key === "ArrowUp") { e.preventDefault(); move(-1); return; }
          if (!typed && !e.altKey && !e.ctrlKey && !e.metaKey
              && /^[1-9]$/.test(e.key) && chips[Number(e.key) - 1]) {
            e.preventDefault();
            take(used[Number(e.key) - 1]);
            return;
          }
          if (e.key === "Enter") {
            e.preventDefault();
            if (at >= 0) { take(used[at]); return; }
            api.close();
            stepDown(cell);
          }
        });
        return input;
      });
    }

    // 메일 칸. **주소는 고를 것이 아니고 도메인만 고른다.**
    //
    // 후보를 띄우는 일 자체는 공통 부품이 한다(`email_hint.js`) — 수정창의
    // 메일 칸도 같은 부품을 쓴다. 같은 조작을 두 벌로 만들면 "`@` 앞을
    // 건드리나" · "언제 닫히나" 같은 판단이 갈려서 어느 쪽으로 들어왔느냐에
    // 따라 화면이 달라진다.
    //
    // **목록 상자를 `api.pop` 안에 세우는 것이 이 자리의 핵심이다.** 밖에
    // 세우면 후보를 누르는 순간 이 편집창의 "바깥을 눌렀나" 판정(`popover` 의
    // `onDown`)에 걸려, **고르기도 전에 저장되고 창이 닫힌다** — #152 가
    // `.cell-pop` 여백에서 고친 것과 같은 함정이다.
    function startEmail(cell, before, type) {
      popover(cell, before, type, function (api) {
        var input = document.createElement("input");
        // `type="email"` 로 두지 않는다. 커서를 끝에 두는 자리가 그 타입을
        // 건너뛰고(`SELECTABLE`), 브라우저가 제 나름의 검사를 얹는다 —
        // 이 칸은 적힌 그대로 저장되는 칸이다.
        input.type = "text";
        input.className = "cell-pop-input one-line";
        input.value = before;
        api.pop.appendChild(input);

        var hint = global.DealflowEmailHint;
        if (hint) {
          hint.attach(input, {
            anchor: api.pop,
            // 고를 것이 없을 때의 Enter — 적힌 그대로 저장하고 **아래 줄
            // 같은 칸**으로. 여기서 초점을 놓으면 메일 칸만 흐름이 끊긴다.
            onEnter: function () { api.close(); stepDown(cell); },
            // 목록이 뜨고 지면 창 높이가 바뀐다(아래로 자랄 자리 판정).
            onResize: api.place
          });
        } else {
          // 부품을 못 불러왔어도 **고치는 것 자체는 되어야 한다.**
          input.addEventListener("keydown", function (e) {
            if (e.isComposing || e.keyCode === 229) return;   // 조합 중에는 비켜선다
            if (e.key === "Enter") {
              e.preventDefault();
              api.close();
              stepDown(cell);
            }
          });
        }
        api.pop.appendChild(hintLine(
          "`@` 까지 치면 도메인 후보가 뜹니다 · Enter 저장 · Esc 취소"));
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
      var field = cell.getAttribute("data-field");
      if (cell.hasAttribute("data-note")) {
        // 그 명단에만 있는 칸(달마다 늘어나는 칸 포함)은 `notes` 묶음으로 간다.
        // 칸이 하나 늘 때마다 서버 스키마에 이름을 또 적지 않아도 되게 —
        // 그렇게 적어 두면 네 곳 중 하나만 빠져도 조용히 저장이 안 된다.
        body.notes = {};
        body.notes[field] = value;
      } else {
        // 숫자 칸은 빈 값이면 null 로 보낸다 — 0 과 '아직 안 적음'은 다르다.
        body[field] = type === "number" ? toStored(value) : value;
      }

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
          // 필터가 이 값을 볼 수 있게 행에도 적어 둔다. 안 적으면 값은
          // 있는데 필터 목록에는 안 나온다(관심도를 채워도 필터가 비었다).
          var fkey = cell.getAttribute("data-filter-key")
            || cell.getAttribute("data-field");
          if (row && row.hasAttribute("data-f-" + fkey)) {
            row.setAttribute("data-f-" + fkey, forFilter(cell, value));
          }
          // 세우는 값도 같은 이유로 행에 적어 둔다(`data-s-*` · table_sort.js).
          // 안 적으면 화면에는 새 이름이 떠 있는데 머리글을 누르면 **옛 이름
          // 자리**에 선다 — 필터가 겪은 것과 같은 어긋남이다.
          if (row && row.hasAttribute("data-s-" + field)) {
            row.setAttribute("data-s-" + field, value);
          }
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

  // 한 칸에 값이 여럿인 칸(선호 투자분야 등)은 화면과 필터의 구분자가 다르다 —
  // 사람에게는 `AI, 헬스케어` 로 보여 주고, 필터는 `|` 로 나눠 **태그 단위**로
  // 거른다. 보이는 그대로 행에 적으면 `AI, 헬스케어` 가 통째로 값 하나가 되어,
  // 고친 그 사람만 목록에서 따로 떨어져 나온다(`AI` 를 골라도 안 걸린다).
  // 서버가 골라 준 후보(`data-suggest`)를 고를 보기 맨 앞으로 옮긴다.
  //
  // **보기를 새로 만들지 않는다.** 후보는 이미 그 칸에 쓰이고 있는 값 중에서
  // 온 것이라(services/sector_hint.py) 목록에 원래 들어 있다 — 순서만 앞으로
  // 당길 뿐이다. 그래서 눌러 저장되는 값도, 저장하는 길도 여느 보기와 똑같다.
  // 목록에 없는 후보(그 사이 사라진 갈래)는 **버린다** — 여기서 되살려 넣으면
  // 쓰이지 않는 값이 제안을 타고 다시 늘어난다.
  //
  // 순서만 바꾸고 값은 그대로 둔다. 고를 것이 줄지도 늘지도 않아야, 후보가
  // 다 틀렸을 때 사람이 아래에서 원래 값을 고를 수 있다.
  function suggestedFirst(used, raw) {
    var suggested = [];
    String(raw || "").split("|").forEach(function (v) {
      var value = v.trim();
      if (value && used.indexOf(value) !== -1 && suggested.indexOf(value) === -1) {
        suggested.push(value);
      }
    });
    var rest = used.filter(function (v) { return suggested.indexOf(v) === -1; });
    return { suggested: suggested, order: suggested.concat(rest) };
  }

  // `data-filter-sep` 이 있는 칸만 나눈다 — 없으면 적힌 그대로가 값 하나다.
  function forFilter(cell, value) {
    var sep = cell.getAttribute("data-filter-sep");
    if (!sep) return value;
    return String(value).split(sep)
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; })
      .join("|");
  }

  // 방향키가 가리키는 곳 — `[줄, 칸]`. 하나는 늘 0 이다.
  var ARROWS = { ArrowDown: [1, 0], ArrowUp: [-1, 0],
                 ArrowRight: [0, 1], ArrowLeft: [0, -1] };

  // 칸이 끝에 딱 붙으면 옆 칸과 구분이 안 간다 — 그만큼 더 민다.
  var EDGE = 12;

  // 초점이 간 칸이 안 보이면 **표를 따라 민다.**
  //
  // 브라우저에 맡길 수 없다. 이 표들은 머리행이 위에 붙어 서 있고(`sticky`)
  // 왼쪽 한두 칸도 붙어 서 있다(`.stick` — 어느 기업 줄인지 잃지 않으려고).
  // 브라우저의 '보이게 하기' 는 붙어 선 칸들을 모르기 때문에 초점을 그 **밑으로**
  // 밀어 넣고 다 됐다고 본다 — 초점은 있는데 사람 눈에는 없다. 표가 화면보다
  // 1,900px 넘게 넓어서 가로로는 아예 화면 밖에 서기도 한다.
  //
  // 그림이 없는 곳(검사의 가짜 DOM)에서는 잰 값이 전부 0 이라 아무 데도 안
  // 민다 — 여기서 터지면 정작 봐야 할 것(키가 어디로 가는가)을 못 본다.
  function reveal(cell) {
    var wrap = cell.closest && cell.closest(".table-wrap");
    if (!wrap || !wrap.getBoundingClientRect || !cell.getBoundingClientRect) return;
    var box, view;
    try {
      box = cell.getBoundingClientRect();
      view = wrap.getBoundingClientRect();
    } catch (err) {
      return;
    }
    if (typeof wrap.scrollLeft === "number") {
      var left = view.left + stuckLeft(cell);
      if (box.left < left) wrap.scrollLeft -= (left - box.left) + EDGE;
      else if (box.right > view.right) wrap.scrollLeft += (box.right - view.right) + EDGE;
    }
    if (typeof wrap.scrollTop === "number") {
      var top = view.top + stuckTop(wrap);
      if (box.top < top) wrap.scrollTop -= (top - box.top) + EDGE;
      else if (box.bottom > view.bottom) wrap.scrollTop += (box.bottom - view.bottom) + EDGE;
    }
  }

  // 왼쪽에 붙어 선 칸들이 덮는 폭. **자기가 그 칸이면 0 이다** — 붙어 선 칸은
  // 밀어도 제자리라 밀어 봐야 헛일이고, 빼 주면 표가 오른쪽으로 튄다.
  function stuckLeft(cell) {
    if (cell.closest && cell.closest(".stick")) return 0;
    var row = cell.closest && cell.closest("tr");
    if (!row) return 0;
    var wide = 0;
    row.querySelectorAll(".stick").forEach(function (el) {
      if (el.getBoundingClientRect) wide += el.getBoundingClientRect().width || 0;
    });
    return wide;
  }

  // 위에 붙어 선 머리행의 키.
  function stuckTop(wrap) {
    var head = wrap.querySelector && wrap.querySelector("thead");
    if (!head || !head.getBoundingClientRect) return 0;
    return head.getBoundingClientRect().height || 0;
  }

  // 커서를 끝에 둔다. **아무 input 에서나 되는 게 아니다** — number·date·email
  // 등은 selectionStart 를 지원하지 않아 setSelectionRange 가 예외를 던진다.
  // 되는 것만 골라 부른다(막는 목록이 아니라 되는 목록으로 둬야 새 타입이
  // 늘어도 안 터진다).
  var SELECTABLE = { "": true, text: true, search: true, url: true, tel: true,
                     password: true };

  function putCaretAtEnd(input, multi, type) {
    if (!input.setSelectionRange) return;
    if (!multi && !SELECTABLE[input.type]) return;
    input.setSelectionRange(input.value.length, input.value.length);
  }

  // 숫자 칸은 빈 값이면 `null` 로 보낸다 — `0` 과 '아직 안 적음'은 다르다.
  //
  // **여기에 단위 환산을 다시 들이지 마라.** 기업 금액 넷이 억↔백만원을 여기서
  // 곱하고 나눴는데(`data-unit="eok"`), 그 자리 때문에 `5-10억 사이` 같은 값을
  // 아예 넣을 수 없었다. 이제 그 넷은 글자 칸이고(0074), 숫자를 뽑는 규칙은
  // `app/services/amount.py` 한 곳이다.
  function toStored(value) {
    if (value === "") return null;
    var n = Number(value);
    return isNaN(n) ? null : n;
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
