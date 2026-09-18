// 담당자 고르기에 **검색을 얹는다** (딜 진행 관리의 두 폼).
//
// ── 무엇이 문제였나 ─────────────────────────────────────────────────────
//
// 고르는 칸에 담당자가 133명 들어 있다. 이름을 알아도 목록을 훑어 내려가야
// 찾을 수 있고, 회사 이름 순으로 서 있어서 이름만 아는 사람은 어디쯤인지
// 짐작도 안 된다.
//
// ── 왜 `<select>` 를 안 바꾸나 ──────────────────────────────────────────
//
// 이 칸이 보내는 값은 **번호**다(`contact_id`). `<input list=…>` +
// `<datalist>` 로 바꾸면 고른 값이 **글자**가 되어, 번호를 숨은 칸에 따로
// 실어 보내야 하고 목록에 없는 글자를 치고 보내는 길이 생긴다. 그래서
// 고르는 칸은 그대로 두고 **그 위에 검색칸을 얹어 보기를 좁힌다** — 딜 제안
// 관리의 담당자 고르기와 같은 결이고(`deals.js` 의 `applyContactFilter`),
// 거르는 재료도 그 화면과 같은 `data-search` 다.
//
// ── 지키는 것 ───────────────────────────────────────────────────────────
//
//   · **고른 사람은 검색어와 무관하게 남는다.** 딜 제안 관리가 정한 그 규칙이다
//     — 검색어를 바꾸다 고른 사람이 사라지면 누구를 골라 뒀는지 알 수 없다.
//   · **검색은 거르기만 한다.** 좁혀졌다고 대신 골라 주지 않는다 — 친 것과
//     저장되는 것이 달라지면 안 된다(`email_hint.js` 의 Enter 규칙과 같다).
//     다만 **하나로 좁혀졌을 때의 Enter** 는 고른다. 거기서는 고를 것이
//     하나뿐이라 달라질 것이 없고, 손이 자판을 떠나지 않는다.
//   · 검색칸의 Enter 가 **폼을 보내지 않는다.** 좁히려고 친 Enter 로 요청이
//     기록되면 안 된다.
//   · 아무도 안 맞으면 고르는 칸이 **빈 보기만 남는다** — `required` 가 막는다.
//     그리고 왜 막히는지 한 줄로 말해 준다(말 안 하면 막다른 길이 된다).
//   · 고른 사람이 바뀌면 `change` 를 **알린다** — 지난 회차 번호를 부르는 쪽이
//     그것을 듣는다(`ir_numbers.js`).
//
// 자산이 안 실려도 폼은 그대로 산다 — 검색칸이 아무 일도 안 하는 칸이 될 뿐,
// `<select>` 는 133명을 그대로 들고 있다.
(function (global) {
  "use strict";

  //: 검색칸이 어느 고르기를 거르는지 적어 두는 자리. **이름이 여기 하나다.**
  var ATTR = "data-contact-pick";
  //: 몇 명으로 좁혀졌는지 적는 줄.
  var NOTE_ATTR = "data-contact-pick-note";

  var NONE_NOTE = "맞는 사람이 없습니다 — 검색어를 지우면 전부 다시 뜹니다";
  var ONE_NOTE = " · Enter 로 고르기";

  //: 붙여 둔 고르기들. 밖에서 초기화할 때 찾는다(아래 `clear`).
  var attached = {};

  // 이 보기가 검색어에 걸리나. 거르는 값은 화면이 실어 둔 `data-search` 다 —
  // 보이는 글자로 맞추면 `·` 같은 꾸밈 글자까지 검색어에 걸린다.
  function hit(option, query) {
    if (!query) return true;
    return (option.getAttribute("data-search") || "").indexOf(query) !== -1;
  }

  function attach(box) {
    var id = box.getAttribute(ATTR);
    if (!id) return null;
    var select = document.getElementById(id);
    if (!select) return null;

    // 처음 그려진 보기들을 통째로 쥔다. 거를 때 **지웠다 다시 세우므로**,
    // 지운 것을 어디선가 들고 있어야 검색어를 지웠을 때 되돌아온다.
    var all = Array.prototype.slice.call(select.querySelectorAll("option"));
    if (all.length < 2) return null;       // 빈 보기뿐 — 거를 것이 없다

    var note = document.querySelector("[" + NOTE_ATTR + "='" + id + "']");
    // 사람이 고를 수 있는 보기 수(맨 앞 빈 보기는 뺀다).
    var total = all.filter(function (o) { return o.value !== ""; }).length;

    function shown() {
      return Array.prototype.slice.call(select.querySelectorAll("option"))
        .filter(function (o) { return o.value !== ""; });
    }

    function apply() {
      var query = (box.value || "").trim().toLowerCase();
      var chosen = select.value;
      var keep = all.filter(function (option) {
        // 빈 보기는 언제나 남는다 — 아무도 안 맞을 때 `required` 가 기댈 자리다.
        if (option.value === "") return true;
        // 고른 사람도 언제나 남는다(딜 제안 관리와 같은 규칙).
        if (chosen && option.value === chosen) return true;
        return hit(option, query);
      });

      // 지웠다 다시 세운다. **보기를 감추는 것**(`option.hidden`)은 브라우저마다
      // 다르게 듣는 성질이라, 어디서는 걸러지고 어디서는 안 걸러진다.
      all.forEach(function (option) {
        if (option.parentNode) option.parentNode.removeChild(option);
      });
      keep.forEach(function (option) { select.appendChild(option); });
      // 골라 둔 값은 그대로 둔다 — 위에서 그 보기를 남겨 두었다.
      select.value = chosen;

      if (!note) return;
      var many = keep.filter(function (o) { return o.value !== ""; }).length;
      if (!query) { note.hidden = true; note.textContent = ""; return; }
      note.hidden = false;
      note.textContent = many
        ? many + " / " + total + "명" + (many === 1 ? ONE_NOTE : "")
        : NONE_NOTE;
    }

    // 고른 사람이 바뀌었다고 **알린다.** 지난 회차 번호는 이 알림을 듣고
    // 불린다(`ir_numbers.js`) — 안 알리면 골라 놓고 번호가 안 뜬다.
    function tell() {
      if (typeof global.Event === "function") {
        select.dispatchEvent(new global.Event("change", { bubbles: true }));
      } else if (select.fire) {
        select.fire("change");            // 아주 작은 DOM(검사)에서의 같은 뜻
      }
    }

    box.addEventListener("input", apply);
    box.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      // 좁히려고 친 Enter 가 **요청을 기록해 버리면 안 된다.**
      e.preventDefault();
      var left = shown();
      // 하나로 좁혀졌을 때만 고른다. 둘 이상이면 무엇이 고를 것인지 알 수
      // 없고, 대신 골라 주는 순간 친 것과 저장된 것이 달라진다.
      if (left.length !== 1) return;
      if (select.value === left[0].value) return;
      select.value = left[0].value;
      apply();
      tell();
    });

    attached[id] = { apply: apply, box: box, select: select };
    apply();
    return attached[id];
  }

  // 검색어를 지우고 전부 되돌린다. **밖에서 `select.value` 를 바꾸는 쪽**이
  // 먼저 부른다(`ir_numbers.js` 의 [미팅 잡기]) — 걸러 둔 채로 값을 넣으면
  // 그 보기가 목록에 없어 값이 안 들어가고, 화면은 엉뚱한 사람을 가리킨다.
  function clear(id) {
    var one = attached[id];
    if (!one) return;
    one.box.value = "";
    one.apply();
  }

  function attachAll() {
    Array.prototype.forEach.call(document.querySelectorAll("[" + ATTR + "]"),
                                 attach);
  }

  global.DealflowContactPick = {
    ATTR: ATTR, NOTE_ATTR: NOTE_ATTR, NONE_NOTE: NONE_NOTE,
    attach: attach, attachAll: attachAll, clear: clear
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachAll);
  } else {
    attachAll();
  }
})(typeof window !== "undefined" ? window : this);
