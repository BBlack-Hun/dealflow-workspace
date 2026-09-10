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
// `.cell` 은 td 가 아니어도 된다. 한 칸에 여러 줄이 들어 있는 표(투자사 관리 현황 처럼
// 메모 밑에 버튼이 붙어 있는 곳)에서는 고칠 줄에만 붙인다 — td 째로 바꾸면
// 같이 들어 있던 버튼이 사라진다.
//
// 칸을 벗어날 때만 저장한다. 글자마다 저장하면 요청이 쏟아진다.
// 칸 안에서 고치는 것은 입력칸을 벗어날 때(blur), **떠서 고치는 창(long·pick)은
// 창 바깥을 눌렀을 때** 끝난다 — 창 안이면 여백이든 보기 목록이든 안 닫힌다.
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

      // **빠져나갈 길을 먼저 만든다.** 아래에서 뭐라도 던지면 blur·Escape 가
      // 안 붙고, editing 이 이 칸에 물린 채 남아 표 전체가 먹통이 된다 —
      // 실제로 그랬다(아래 setSelectionRange 참고).
      input.addEventListener("blur", finish);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { input.value = before; input.blur(); }
        // 여러 줄 칸에서는 엔터가 줄바꿈이어야 한다. 저장은 Ctrl/Cmd+Enter.
        if (e.key === "Enter" && (!multi || e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          input.blur();
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
      }
      document.addEventListener("pointerdown", onDown, true);
      document.addEventListener("keydown", onKey);

      place();
      try {
        input.focus();
        putCaretAtEnd(input, input.tagName === "TEXTAREA", "");
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
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            api.close();
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

        if (used.length) {
          var box = document.createElement("div");
          box.className = "cell-pop-choices";
          used.forEach(function (value) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "cell-pop-choice" + (value === before ? " on" : "")
              + (suggested.indexOf(value) !== -1 ? " suggested" : "");
            chip.textContent = value;
            if (suggested.indexOf(value) !== -1) {
              chip.title = "한줄 소개를 보고 고른 후보입니다 — 맞는지 보고 고르세요";
            }
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
          suggested.length
            ? "앞 " + suggested.length + "개는 한줄 소개를 보고 고른 후보입니다 "
              + "— 맞는 것이 없으면 아래에서 고르세요 · Enter 저장 · Esc 취소"
            : used.length ? "골라 누르거나 새로 적습니다 · Enter 저장 · Esc 취소"
                          : "Enter 저장 · Esc 취소"));

        input.addEventListener("keydown", function (e) {
          if (e.key === "Enter") { e.preventDefault(); api.close(); }
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
