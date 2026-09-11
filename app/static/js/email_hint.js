// 메일 칸에 **치는 대로 `친글자@도메인` 후보를 띄운다.**
//
// ── 왜 `<datalist>` 가 아닌가 ────────────────────────────────────────────
//
// 브라우저의 `<datalist>` 는 친 글자를 **앞에서부터** 맞춘다. `hong@` 까지
// 쳤을 때 `@example.com` 은 그 글자로 시작하지 않으니 걸리지 않는다 — 분야
// 칸들이 쓰는 그 방식(`companies.html` 의 `opts-sector_*`)을 여기에는 그대로
// 못 쓴다. 그래서 이 부품이 따로 있다.
//
// ── 도메인 목록은 **어디서 오나** ────────────────────────────────────────
//
// 화면이 그려 둔 칸 하나(`#opts-email-domain`)에서만 읽는다. 그 칸의 값을
// 만드는 자리도 하나다(`app/services/email_domains.py`) — 재료는 그 화면이
// 지금 그리고 있는 줄들이라, 표에 보이는 것과 후보가 갈릴 자리가 없다.
// 목록을 여기 박아 두지 않는 이유는 분야 칸과 같다: 투자사가 늘면 도메인도
// 는다.
//
// ── 저장 흐름을 안 깨는 자리 (#152 와 같은 함정) ────────────────────────
//
// 이 목록은 **`blur` 에 아무것도 걸지 않는다.** 이 저장소의 표 편집은 칸 안
// 입력이 `blur` 될 때 저장되는 자리가 있어서(`inline_edit.js` 의 보통 칸),
// 후보를 누르는 순간 `blur` 가 나면 **고르기도 전에 저장되고 창이 닫힌다.**
// #152 가 `.cell-pop` 에서 고친 것이 정확히 그 부류다.
//
// 그래서 세 겹으로 막는다.
//
//   1. 후보는 `mousedown` 에서 `preventDefault()` 한다 — 초점이 입력칸을
//      떠나지 않으므로 `blur` 자체가 안 난다(`startPick` 이 쓰던 방법).
//   2. 닫는 판단은 `blur` 가 아니라 **문서의 `pointerdown` 안팎**으로 한다
//      (`.cell-pop` 과 같은 방법).
//   3. 목록 상자를 **불러 준 쪽이 준 자리 안에** 세운다(`opts.anchor`).
//      표 칸에서는 `.cell-pop` 안이라, 목록을 눌러도 편집창의 "바깥을 눌렀나"
//      판정에 안 걸린다. `document.body` 에 띄우면 그 판정에 걸려 창이 먼저
//      닫힌다 — 보이는 자리는 같은데 결과가 정반대인 자리다.
//      (보이는 자리는 `position: fixed` 로 잡으므로 부모가 좁아도 안 잘린다)
//
// ── 지켜야 하는 것 ───────────────────────────────────────────────────────
//
//   · `@` 앞은 **한 글자도 안 건드린다.** 고르면 친 글자 뒤에 도메인만 붙는다.
//   · 안 골라도 그만이다. 목록에 없는 도메인을 쳐도 그대로 저장된다 —
//     Enter 는 **골라 둔 것이 있을 때만** 고르고, 없으면 그냥 저장으로 간다.
//     (열려 있다는 이유로 첫 줄을 대신 골라 주면, 사람이 친 것과 저장된 것이
//      달라진다)
//   · `Esc` 는 목록만 닫는다. 한 번 더 누르면 그때 창이 닫힌다.
(function (global) {
  "use strict";

  // 화면이 도메인 목록을 실어 두는 칸. **이름이 여기 하나다.**
  var LIST_ID = "opts-email-domain";

  // 한 번에 세우는 후보 수.
  //
  // 서버가 이미 "두 번 이상 쓰인 도메인" 으로 잘라 주지만, 투자사 명단은 그래도
  // 97가지다(`services/email_domains.py` 의 재 둔 값). 97줄이 한 번에 서면
  // 고르는 것보다 치는 것이 빠르다 — 목록이 방해가 되는 순간이다.
  //
  // 여덟인 이유: 표 칸 위의 편집창이 440px 이고 도메인 딱지가 줄당 서넛이라
  // 여덟이 두 줄이다. 세 줄을 넘기면 아래 안내줄이 화면 밖으로 밀린다.
  // 자른 것은 **말해 준다**(아래 `note`) — 안 보이는 것이 없는 것으로 읽히면
  // 사람이 목록을 뒤진다.
  var MAX_SHOWN = 8;

  var CUT_NOTE = "두 번 이상 쓰인 도메인만 뜹니다";
  var KEY_NOTE = "↑↓ Enter 로 고르기 · Esc 로 닫기";

  // ── 도메인 목록을 읽는 **한 곳** ───────────────────────────────────────
  function domains() {
    var node = document.getElementById(LIST_ID);
    if (!node) return [];
    var parsed;
    try {
      parsed = JSON.parse(node.getAttribute("data-domains") || "[]");
    } catch (err) {
      return [];               // 값이 깨져 있어도 칸은 그냥 글자 칸으로 산다
    }
    if (!parsed || typeof parsed.length !== "number") return [];
    var out = [];
    for (var i = 0; i < parsed.length; i += 1) {
      var one = String(parsed[i] == null ? "" : parsed[i]).trim().toLowerCase();
      if (one && out.indexOf(one) === -1) out.push(one);
    }
    return out;
  }

  // ── 친 글자를 `@` 에서 가른다 ──────────────────────────────────────────
  //
  // `local` 에는 `@` 까지가 통째로 들어 있다. 고를 때 이 글자를 **그대로 앞에
  // 두고** 뒤만 갈아 끼우므로, `@` 앞이 바뀔 길이 없다.
  // `@` 가 여럿이면 **마지막** 것을 본다 — 지금 치고 있는 자리가 거기다.
  function split(value) {
    var text = String(value == null ? "" : value);
    var at = text.lastIndexOf("@");
    if (at < 0) return null;          // 아직 `@` 를 안 쳤다 — 띄울 것이 없다
    return { local: text.slice(0, at + 1), query: text.slice(at + 1).toLowerCase() };
  }

  // 지금 친 글자에 맞는 도메인들. **자르기 전** 목록이다(세는 쪽이 쓴다).
  function matches(list, value) {
    var parts = split(value);
    if (!parts) return [];
    var query = parts.query;
    // 띄어쓰기가 섞였으면 도메인을 치는 중이 아니다(메모를 적고 있거나 값이 둘).
    if (/\s/.test(query)) return [];
    var hit = (list || []).filter(function (one) { return one.indexOf(query) === 0; });
    // 이미 다 쳤으면 안 띄운다. 친 글자와 똑같은 후보 한 줄은 고를 것이 아니라
    // 가리는 것이다 — 저장하려고 Enter 를 치는 손 앞을 막는다.
    if (hit.length === 1 && hit[0] === query) return [];
    return hit;
  }

  // ── 칸 하나에 목록을 붙인다 ────────────────────────────────────────────
  //
  // opts.anchor   목록 상자를 **어느 자리 안에** 세울까. 표 칸에서는 편집창
  //               (`.cell-pop`) 안이어야 한다 — 위 주석 3번.
  // opts.domains  쓸 목록(안 주면 화면에서 읽는다)
  // opts.onEnter  고를 것이 없을 때의 Enter. 표 칸에서는 "저장하고 닫기".
  // opts.onResize 목록이 뜨고 지면서 자리를 다시 잡아야 하는 쪽(편집창)
  function attach(input, opts) {
    if (!input) return null;
    opts = opts || {};
    var list = opts.domains || domains();
    var host = opts.anchor || input.parentNode;
    if (!host) return null;

    var box = document.createElement("div");
    box.className = "email-hint";
    box.hidden = true;
    host.appendChild(box);

    var shown = [];
    var active = -1;           // 아직 아무것도 안 골랐다. **-1 이 기본**이다
    var dead = false;

    function close() {
      if (box.hidden && !shown.length) return;
      shown = [];
      active = -1;
      box.hidden = true;
      box.innerHTML = "";
      if (opts.onResize) opts.onResize();
    }

    // 칸 바로 아래. **화면 밖으로 나가지 않게 왼쪽으로 당긴다** — 수정창의
    // 메일 칸은 오른쪽 끝에 붙어 있어서, 안 당기면 목록의 오른쪽이 잘린다.
    function place() {
      var rect = input.getBoundingClientRect();
      box.style.position = "fixed";
      box.style.minWidth = Math.max(180, Math.round(rect.width)) + "px";
      box.style.top = Math.round(rect.bottom + 2) + "px";
      var width = box.offsetWidth || Math.max(180, rect.width);
      var room = (global && global.innerWidth) || 0;
      var left = room ? Math.min(rect.left, room - width - 8) : rect.left;
      box.style.left = Math.round(Math.max(8, left)) + "px";
    }

    // 친 글자 뒤만 갈아 끼운다.
    function pick(domain) {
      var parts = split(input.value);
      if (!parts) return;
      input.value = parts.local + domain;
      close();
      try { input.focus(); } catch (err) { /* 초점은 곁가지다 */ }
      if (opts.onPick) opts.onPick(input.value);
    }

    function paint() {
      Array.prototype.forEach.call(box.querySelectorAll(".email-hint-item"),
        function (node, i) { node.classList.toggle("on", i === active); });
    }

    function render() {
      var hit = matches(list, input.value);
      if (!hit.length) { close(); return; }

      shown = hit.slice(0, MAX_SHOWN);
      active = -1;
      box.innerHTML = "";
      shown.forEach(function (domain) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "email-hint-item";
        item.textContent = domain;
        // `mousedown` 이라야 초점이 입력칸을 떠나기 전에 잡힌다 — 위 주석 1번.
        item.addEventListener("mousedown", function (e) {
          e.preventDefault();
          pick(domain);
        });
        box.appendChild(item);
      });

      var note = document.createElement("div");
      note.className = "email-hint-note";
      var extra = hit.length - shown.length;
      note.textContent = (extra > 0 ? "외 " + extra + "개 — 더 치면 좁혀집니다"
                                    : CUT_NOTE) + " · " + KEY_NOTE;
      box.appendChild(note);

      box.hidden = false;
      place();
      if (opts.onResize) opts.onResize();
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
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (move(e.key === "ArrowDown" ? 1 : -1)) e.preventDefault();
        return;
      }
      if (e.key === "Enter") {
        // **골라 둔 것이 있을 때만** 고른다. 없으면 목록을 닫고 저장으로 보낸다 —
        // 목록이 떠 있다는 이유로 대신 골라 주면 친 것과 저장된 것이 달라진다.
        if (!box.hidden && active >= 0) {
          e.preventDefault();
          e.stopPropagation();
          pick(shown[active]);
          return;
        }
        close();
        if (opts.onEnter) { e.preventDefault(); opts.onEnter(); }
        return;
      }
      if (e.key === "Escape" && !box.hidden) {
        // 목록만 닫는다. 한 번 더 누르면 그때 창이 닫힌다(위로 안 올린다).
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    });

    // 닫는 판단은 **`blur` 가 아니라** 문서의 `pointerdown` 안팎이다 — 위 주석 2번.
    function onDown(e) {
      if (!alive()) { destroy(); return; }
      if (box.contains(e.target) || e.target === input) return;
      close();
    }
    // 목록을 달아 준 자리(표 칸의 편집창)가 통째로 사라진 뒤에도 문서에 손이
    // 남아 있으면 안 된다 — 칸을 열 때마다 하나씩 쌓인다.
    function alive() {
      var node = box;
      while (node) { if (node === document.body) return true; node = node.parentNode; }
      return false;
    }
    function destroy() {
      if (dead) return;
      dead = true;
      document.removeEventListener("pointerdown", onDown, true);
      if (global) {
        global.removeEventListener("scroll", follow, true);
        global.removeEventListener("resize", follow);
      }
    }
    // 떠 있는 동안 칸을 따라다닌다. 상자가 `position: fixed` 라, 안 따라가면
    // 수정창을 굴리는 순간 목록만 그 자리에 남는다(`.cell-pop` 과 같은 처리).
    function follow() { if (!box.hidden) place(); }
    document.addEventListener("pointerdown", onDown, true);
    if (global) {
      global.addEventListener("scroll", follow, true);
      global.addEventListener("resize", follow);
    }

    return { render: render, close: close, destroy: destroy, box: box };
  }

  // 화면이 `data-email-hint` 를 달아 둔 칸에 전부 붙인다(수정창의 메일 칸).
  // 이름을 여기 적어 두지 않는다 — 칸이 하나 늘 때 여기 넣는 것을 잊으면
  // 화면은 멀쩡한데 그 칸만 조용히 후보가 안 뜬다.
  function attachAll() {
    var list = domains();
    Array.prototype.forEach.call(
      document.querySelectorAll("input[data-email-hint]"), function (input) {
        if (input.getAttribute("data-email-hint-on")) return;
        input.setAttribute("data-email-hint-on", "1");
        attach(input, { domains: list });
      });
  }

  global.DealflowEmailHint = {
    LIST_ID: LIST_ID,
    MAX_SHOWN: MAX_SHOWN,
    domains: domains,
    split: split,
    matches: matches,
    attach: attach,
    attachAll: attachAll
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachAll);
  } else {
    attachAll();
  }
})(window);
