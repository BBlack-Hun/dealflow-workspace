// 문구 관리 화면의 **문구 검색** (11/11 팀 요청 — "단어나 문장으로 검색").
//
// 문구가 마흔 개를 넘고 종류도 스무 가지가 넘는다. 어느 구간에 있는지 모르는
// 문구를 찾으려면 화면을 통째로 훑어야 했다.
//
// ── 무엇으로 찾나 ───────────────────────────────────────────────────────
//
// 문구 하나가 싣는 글자 = 그 구간 제목줄(종류 이름 · 딜 제안 관리 탭 · 설명) +
// 갈래 이름(딜 소싱) + 문구 이름 + 꼬리표(팀 기본 · 내 문구 …) + 본문.
// 제목줄은 **화면에 그려진 글자를 그대로 읽는다** — 서버에서 한 벌 더 실으면
// 설명을 고친 날 화면 글자와 찾는 글자가 갈린다.
//
// 이름·본문은 **지금 칸에 들어 있는 값**(`.value`)으로 본다. 고치다 만 문구도
// 고친 글자로 찾아진다.
//
// "실제로 나가는 문구" 미리보기와 [내가 쓸 문구] 고르기 목록은 안 본다 —
// 미리보기에는 인사말이 다 붙어 있어서 `안녕하세요` 한 마디에 모든 구간이 걸린다.
//
// ── 맞추는 규칙 ─────────────────────────────────────────────────────────
//
//   · 대소문자 · 띄어쓰기 · 줄바꿈을 따지지 않는다(`딜제안` 으로 `딜 제안` 이 걸린다).
//   · 띄어 쓴 여러 낱말은 **모두** 들어 있어야 걸린다 — 문장을 통째로 붙여 넣어도
//     그 낱말들이 다 든 문구가 걸린다.
//   · 구간 제목줄이 걸리면 그 구간 문구가 전부 남는다(제목줄이 문구마다 실리므로).
//   · 남은 문구가 없는 갈래 · 구간은 제목째 감춘다. 하나도 안 걸리면 `검색 결과 없음`.
//   · 접혀 있는 `그 밖의 문구` 는 안에 걸린 것이 있으면 펴고, 없으면 감춘다.
//     검색어를 지우면 검색 전의 접힘 그대로 돌아간다.
//
// ── 지키는 것 ───────────────────────────────────────────────────────────
//
// **`hidden` 만 켰다 끈다 — 다시 그리지 않는다.** 저장 안 한 칸이 그대로 남아야
// 한다. 그리고 문구 칸을 고칠 때는 다시 거르지 않는다 — 고치는 중인 문구가 검색어에서
// 벗어났다고 눈앞에서 사라지면 안 된다(검색칸에 칠 때만 거른다).
(function () {
  "use strict";

  var box = document.getElementById("tpl-search");
  if (!box) return;
  var note = document.getElementById("tpl-search-note");
  var empty = document.getElementById("tpl-search-empty");
  var others = document.getElementById("others");

  // 칸과 칸 사이에 끼우는 글자 — 띄어쓰기를 다 걷어내므로, 이것이 없으면 이름 끝과
  // 본문 첫 글자가 붙어 한 낱말처럼 걸린다. 자판으로 칠 수 없는 글자다.
  var SEP = "\u0001";

  //: 검색을 시작하기 전 `그 밖의 문구` 가 펴져 있었나 — 지우면 그대로 되돌린다.
  var othersWasOpen = null;

  function list(nodes) { return Array.prototype.slice.call(nodes || []); }

  function norm(text) {
    return String(text || "").toLowerCase().replace(/\s+/g, "");
  }

  function words(query) {
    return String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
  }

  function hits(hay, ws) {
    return ws.every(function (w) { return hay.indexOf(w) !== -1; });
  }

  function texts(root, selector) {
    return list(root.querySelectorAll(selector)).map(function (el) {
      return norm(el.textContent);
    }).join(SEP);
  }

  // 문구 하나의 글자 — 지금 칸에 든 값으로.
  function rowHay(row) {
    var name = row.querySelector("input[name=\"name\"]");
    var body = row.querySelector("textarea");
    return [name ? norm(name.value) : "", texts(row, ".tpl-head .tag"),
            body ? norm(body.value) : ""].join(SEP);
  }

  function apply() {
    var ws = words(box.value);
    var on = ws.length > 0;
    var total = 0, shown = 0, sections = 0;
    var othersHit = false;

    // 구간 = 제목줄(`tpl-kind-title`)을 든 `.panel`. 구간 태그에 표시를 따로 달지
    // 않는다 — 그 여는 태그 모양으로 구간을 잘라 보는 검사가 있다.
    list(document.querySelectorAll(".tpl-kind-title")).forEach(function (head) {
      var sec = head.closest(".panel");
      if (!sec) return;
      var secHay = norm(head.textContent);
      var secHit = !on || hits(secHay, ws);
      var anySlot = false;
      list(sec.querySelectorAll(".tpl-slot")).forEach(function (slot) {
        var slotHay = secHay + SEP + texts(slot, "h3");
        var slotHit = !on || hits(slotHay, ws);
        var anyRow = false;
        list(slot.querySelectorAll("[data-tpl-row]")).forEach(function (row) {
          var hit = !on || hits(slotHay + SEP + rowHay(row), ws);
          row.hidden = !hit;
          total += 1;
          if (hit) { shown += 1; anyRow = true; }
        });
        // 문구가 하나도 없는 갈래도 이름이 걸리면 남긴다 — 거기서 새로 만든다.
        slot.hidden = !(slotHit || anyRow);
        if (!slot.hidden) anySlot = true;
      });
      sec.hidden = !(secHit || anySlot);
      if (!sec.hidden) {
        sections += 1;
        if (others && others.contains(sec)) othersHit = true;
      }
    });

    if (others) {
      if (on) {
        if (othersWasOpen === null) othersWasOpen = !!others.open;
        others.hidden = !othersHit;
        others.open = othersHit || othersWasOpen;
      } else {
        others.hidden = false;
        if (othersWasOpen !== null) others.open = othersWasOpen;
        othersWasOpen = null;
      }
    }
    if (note) {
      note.hidden = !on;
      note.textContent = on ? shown + " / " + total + "개 표시 중" : "";
    }
    if (empty) empty.hidden = !on || sections > 0;
  }

  box.addEventListener("input", apply);
  // 뒤로 가기로 돌아오면 브라우저가 검색어를 되살려 둘 때가 있다 — 그 글자대로 거른다.
  if (box.value) apply();
})();
