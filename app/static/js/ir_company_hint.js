// 「요청받은 기업」 칸에 **치는 줄에만** 기업명 후보를 띄운다.
//
// ── 왜 `<datalist>` 가 아닌가 ───────────────────────────────────────────
//
// 이 칸은 `<textarea>` 다. 투자사가 한 번에 여러 곳을 요청하는 일이 잦아서
// **줄바꿈으로 여러 개**를 적는다. `<datalist>` 는 한 줄 입력칸(`<input>`)에만
// 붙고, 붙는다 해도 칸 값 **전체**를 하나로 보고 맞춘다 — 둘째 줄을 치는
// 중에는 아무것도 못 맞춘다. 게다가 브라우저의 `<datalist>` 는 친 글자를
// **앞에서부터** 맞춰서, 이름 가운데 글자로는 찾을 수 없다(`email_hint.js` 가
// 따로 있는 이유와 같다).
//
// 그래서 칸 모양도 보내는 값도 그대로 두고, **지금 치고 있는 조각**에만
// 후보를 띄운다.
//
// ── 번호로 적는 길을 안 깬다 ───────────────────────────────────────────
//
// 이 칸은 `2, 4` 처럼 **번호로 적어도 되는** 칸이다. 서버는 조각이 숫자뿐이면
// 지난 회차의 자리 번호로 읽고, 아니면 기업 이름으로 읽는다
// (`services/pipeline.py` 의 `resolve_request_names`). 그래서
//
//   · 숫자만 친 조각에는 **후보를 안 띄운다.** 거기서 이름을 넣어 주면 번호로
//     적으려던 줄이 이름 줄로 바뀐다 — 뜻이 달라지는 자리다.
//   · 조각을 가르는 글자도 서버와 **같다**: 줄바꿈과 쉼표. 서버가 쉼표로도
//     가르므로(`raw.replace(",", "\n")`) `2, 샘플` 의 `샘플` 은 그 자체로
//     한 조각이고, 여기서도 그 조각만 갈아 끼운다.
//   · `지난 회차에서 고르기`(`ir_numbers.js` 의 번호 딱지)가 넣는 값도 그대로
//     산다 — 그쪽은 칸 값을 줄 단위로 다시 쓰고, 이 부품은 쓰는 사람이
//     타이핑할 때만 움직인다.
//
// ── 후보 목록은 어디서 오나 ────────────────────────────────────────────
//
// 화면이 그려 둔 칸 하나(`#opts-ir-company`)에서만 읽는다. 서버가 화면을
// 그릴 때 **한 번** 실어 준다(`routers/ir.py` 의 `_company_names`) — 타이핑할
// 때마다 물으면 이름 한 줄을 적는 동안 질의가 열 번 넘게 나간다. 메일 도메인
// 후보와 같은 방식이다.
//
// ── 저장 흐름을 안 깨는 자리 ───────────────────────────────────────────
//
// `email_hint.js` 가 겪은 그 함정을 그대로 피한다.
//
//   1. 후보는 `mousedown` 에서 `preventDefault()` — 초점이 칸을 안 떠난다.
//   2. 닫는 판단은 `blur` 가 아니라 문서의 `pointerdown` 안팎으로 한다.
//   3. Enter 는 **짚어 둔 것이 있을 때만** 고른다. 없으면 평소처럼 줄바꿈이다
//      — 열려 있다는 이유로 첫 줄을 대신 골라 주면 친 것과 적히는 것이 달라진다.
//   4. `Esc` 는 목록만 닫는다.
//   5. 후보가 없으면 **조용히 아무 일도 안 한다.**
(function (global) {
  "use strict";

  //: 후보 이름을 싣는 칸. **이름이 여기 하나다.**
  var LIST_ID = "opts-ir-company";
  //: 후보를 붙일 칸에 화면이 달아 두는 표시.
  var HOOK = "data-company-hint";

  // 한 번에 세우는 후보 수. 기업이 344곳이라 안 자르면 칸을 통째로 덮는다.
  // 자른 것은 **말해 준다** — 안 보이는 것이 없는 것으로 읽히면 사람이 목록을
  // 뒤진다(`email_hint.js` 와 같은 뜻).
  var MAX_SHOWN = 8;

  var KEY_NOTE = "↑↓ Enter 로 고르기 · Esc 로 닫기";

  //: 조각을 가르는 글자 — **서버와 같다**(줄바꿈과 쉼표).
  var SEPS = ["\n", ","];

  // ── 후보 목록을 읽는 **한 곳** ─────────────────────────────────────────
  function names() {
    var node = document.getElementById(LIST_ID);
    if (!node) return [];
    var parsed;
    try {
      parsed = JSON.parse(node.getAttribute("data-names") || "[]");
    } catch (err) {
      return [];               // 값이 깨져 있어도 칸은 그냥 글자 칸으로 산다
    }
    if (!parsed || typeof parsed.length !== "number") return [];
    var out = [];
    for (var i = 0; i < parsed.length; i += 1) {
      var one = String(parsed[i] == null ? "" : parsed[i]).trim();
      if (one && out.indexOf(one) === -1) out.push(one);
    }
    return out;
  }

  // ── 지금 치고 있는 조각 ────────────────────────────────────────────────
  //
  // 커서가 있는 자리에서 앞뒤로 구분자를 찾아 **그 사이 한 조각**을 집는다.
  // 앞뒤의 띄어쓰기는 조각에 넣지 않는다 — `2, 샘플` 의 조각은 `샘플` 이고,
  // 갈아 끼울 때도 그 자리만 바뀌어야 `2, ` 가 그대로 남는다.
  function token(value, cursor) {
    var text = String(value == null ? "" : value);
    var at = typeof cursor === "number" ? cursor : text.length;
    if (at < 0) at = 0;
    if (at > text.length) at = text.length;

    var start = 0;
    var i;
    for (i = 0; i < SEPS.length; i += 1) {
      var back = text.lastIndexOf(SEPS[i], at - 1);
      if (back >= 0 && back + 1 > start) start = back + 1;
    }
    var end = text.length;
    for (i = 0; i < SEPS.length; i += 1) {
      var fwd = text.indexOf(SEPS[i], at);
      if (fwd >= 0 && fwd < end) end = fwd;
    }
    while (start < end && /\s/.test(text.charAt(start))) start += 1;
    while (end > start && /\s/.test(text.charAt(end - 1))) end -= 1;
    return { start: start, end: end, text: text.slice(start, end) };
  }

  // 지금 친 조각에 맞는 이름들. **자르기 전** 목록이다(세는 쪽이 쓴다).
  //
  // 앞에서 맞는 것을 먼저 세우고 가운데에서 맞는 것을 뒤에 세운다 — 브라우저
  // `<datalist>` 가 앞쪽만 맞춰서 못 찾던 이름이 여기서는 나온다.
  function matches(list, query) {
    var raw = String(query == null ? "" : query).trim();
    if (!raw) return [];
    // 번호로 친 조각에는 이름을 안 권한다 — 여기서 이름을 넣어 주면 뜻이
    // 바뀐다. 받는 모양은 서버와 같다(`deal_numbers.parse_label`):
    // `2` · `기업2` · `[기업2]`.
    if (/^\[?\s*(기업\s*)?\d+\s*\]?$/.test(raw)) return [];
    var key = raw.toLowerCase();
    var head = [], body = [];
    (list || []).forEach(function (one) {
      var at = one.toLowerCase().indexOf(key);
      if (at === 0) head.push(one);
      else if (at > 0) body.push(one);
    });
    var hit = head.concat(body);
    // 이미 다 쳤으면 안 띄운다. 친 글자와 똑같은 후보 한 줄은 고를 것이 아니라
    // 손 앞을 가리는 것이다.
    if (hit.length === 1 && hit[0].toLowerCase() === key) return [];
    return hit;
  }

  // ── 칸 하나에 목록을 붙인다 ────────────────────────────────────────────
  function attach(input, opts) {
    if (!input) return null;
    opts = opts || {};
    var list = opts.names || names();
    var host = opts.anchor || input.parentNode;
    if (!host) return null;

    var box = document.createElement("div");
    box.className = "name-hint";
    box.hidden = true;
    host.appendChild(box);

    var shown = [];
    var active = -1;           // 아직 아무것도 안 짚었다. **-1 이 기본**이다
    var spot = null;           // 마지막으로 그린 조각의 자리

    function close() {
      if (box.hidden && !shown.length) return;
      shown = [];
      active = -1;
      spot = null;
      box.hidden = true;
      box.innerHTML = "";
    }

    // 칸 아래. 화면 밖으로 나가지 않게 왼쪽으로 당긴다(`email_hint.js` 와 같다).
    function place() {
      var rect = input.getBoundingClientRect();
      box.style.position = "fixed";
      box.style.minWidth = Math.max(180, Math.round(rect.width)) + "px";
      box.style.top = Math.round(rect.bottom + 2) + "px";
      var width = box.offsetWidth || Math.max(180, rect.width);
      var room = (global && global.innerWidth) || 0;
      var left = room ? Math.min(rect.left, room - width - 8) : rect.left;
      box.style.left = Math.round(Math.max(8, left)) + "px";
      // **자리를 잡은 뒤 한 번 더 본다.** 위의 `offsetWidth` 는 상자를 세우기
      // 전 값이라 실제보다 좁게 나올 때가 있고, 그러면 390px 화면에서 오른쪽
      // 끝이 화면에 딱 붙거나 넘어간다. 그려진 뒤의 폭으로 다시 당긴다.
      if (!room) return;
      var made = box.getBoundingClientRect();
      if (made.right > room - 8) {
        box.style.left = Math.round(Math.max(8, room - made.width - 8)) + "px";
      }
    }

    function cursor() {
      return typeof input.selectionStart === "number"
        ? input.selectionStart : String(input.value || "").length;
    }

    // **그 조각만** 갈아 끼운다. 다른 줄은 한 글자도 안 건드린다.
    function pick(name) {
      var at = spot || token(input.value, cursor());
      var text = String(input.value || "");
      input.value = text.slice(0, at.start) + name + text.slice(at.end);
      var caret = at.start + name.length;
      close();
      try {
        input.focus();
        if (input.setSelectionRange) input.setSelectionRange(caret, caret);
      } catch (err) { /* 초점은 곁가지다 */ }
      if (opts.onPick) opts.onPick(name);
    }

    function paint() {
      Array.prototype.forEach.call(box.querySelectorAll(".name-hint-item"),
        function (node, i) { node.classList.toggle("on", i === active); });
    }

    function render() {
      var at = token(input.value, cursor());
      var hit = matches(list, at.text);
      // 후보가 없으면 **조용히** 닫는다 — 안내도 경고도 없다.
      if (!hit.length) { close(); return; }

      spot = at;
      shown = hit.slice(0, MAX_SHOWN);
      active = -1;
      box.innerHTML = "";
      shown.forEach(function (name) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "name-hint-item";
        item.textContent = name;
        // `mousedown` 이라야 초점이 칸을 떠나기 전에 잡힌다.
        item.addEventListener("mousedown", function (e) {
          e.preventDefault();
          pick(name);
        });
        box.appendChild(item);
      });

      var note = document.createElement("div");
      note.className = "name-hint-note";
      var extra = hit.length - shown.length;
      note.textContent = (extra > 0 ? "외 " + extra + "곳 — 더 치면 좁혀집니다 · " : "")
        + KEY_NOTE;
      box.appendChild(note);

      box.hidden = false;
      place();
    }

    function move(step) {
      if (!shown.length) { render(); if (!shown.length) return false; }
      active = active < 0
        ? (step > 0 ? 0 : shown.length - 1)
        : (active + step + shown.length) % shown.length;
      paint();
      return true;
    }

    input.addEventListener("input", render);
    // 커서만 옮겨도 치고 있는 조각이 달라진다 — 그때는 **닫는다.** 안 닫으면
    // 다른 줄을 가리키는 옛 목록이 떠 있고, Enter 가 엉뚱한 줄을 갈아 끼운다.
    input.addEventListener("click", close);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!box.hidden && move(e.key === "ArrowDown" ? 1 : -1)) e.preventDefault();
        return;
      }
      if (e.key === "ArrowLeft" || e.key === "ArrowRight" ||
          e.key === "Home" || e.key === "End") {
        close();
        return;
      }
      if (e.key === "Enter") {
        // **짚어 둔 것이 있을 때만** 고른다. 없으면 평소처럼 줄바꿈이다 —
        // 이 칸은 여러 줄을 적는 칸이라 Enter 를 뺏으면 안 된다.
        if (!box.hidden && active >= 0) {
          e.preventDefault();
          e.stopPropagation();
          pick(shown[active]);
        }
        return;
      }
      if (e.key === "Escape" && !box.hidden) {
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    });

    // 닫는 판단은 **`blur` 가 아니라** 문서의 `pointerdown` 안팎이다.
    document.addEventListener("pointerdown", function (e) {
      if (box.contains(e.target) || e.target === input) return;
      close();
    }, true);
    // 떠 있는 동안 칸을 따라다닌다(상자가 `position: fixed` 다).
    if (global && global.addEventListener) {
      global.addEventListener("scroll", function () {
        if (!box.hidden) place();
      }, true);
      global.addEventListener("resize", function () {
        if (!box.hidden) place();
      });
    }

    return { render: render, close: close, pick: pick, box: box };
  }

  // 화면이 표시를 달아 둔 칸에 전부 붙인다. 이름을 여기 적어 두지 않는다 —
  // 칸이 하나 늘 때 여기 넣는 것을 잊으면 그 칸만 조용히 후보가 안 뜬다.
  function attachAll() {
    var list = names();
    if (!list.length) return;              // 실어 준 후보가 없으면 아무 일도 안 한다
    Array.prototype.forEach.call(
      document.querySelectorAll("[" + HOOK + "]"), function (input) {
        if (input.getAttribute(HOOK + "-on")) return;
        input.setAttribute(HOOK + "-on", "1");
        attach(input, { names: list });
      });
  }

  global.DealflowCompanyHint = {
    LIST_ID: LIST_ID, HOOK: HOOK, MAX_SHOWN: MAX_SHOWN,
    names: names, token: token, matches: matches,
    attach: attach, attachAll: attachAll
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachAll);
  } else {
    attachAll();
  }
})(typeof window !== "undefined" ? window : this);
