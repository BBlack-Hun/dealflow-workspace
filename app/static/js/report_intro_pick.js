// 업무 보고 `소개 후보` — 체크한 기업을 담아 딜 제안 관리(딜 소개)를 연다(#164).
//
// 팀원 요청: "딜소개 안한기업 … 체크박스 클릭해서 > 딜 소개를 할수 있게".
//
// **보내는 길을 새로 만들지 않는다.** 이 단추는 링크일 뿐이다 — 딜 제안 관리가 이미
// 받는 `?companies=…`(IR 관리의 [자료 보내기]와 같은 주소 꼴)로 열고, 받는 분 · 문구 ·
// 미리보기 · 확인창 · 발송 시간 관문은 그 화면이 그대로 한다(`deals.js` 의 `applyIncoming`).
//   ① 아무것도 안 골랐으면 잠긴다 — 보이는 줄 전부로 슬쩍 대신하지 않는다
//   ② 한 번에 담을 수 있는 수(`data-max` — `MAX_COMPANIES_PER_SEND`)를 넘으면 잠그고 말한다
//   ③ 주소의 기업 차례 = 표의 차례(금액 높은 순) — 딜 제안 관리가 그 차례로 번호를 붙인다
//   ④ `더 보기` 안에 접힌 줄의 체크도 센다
(function () {
  "use strict";
  var btn = document.getElementById("intro-left-send");
  if (!btn) return;
  var hint = document.getElementById("intro-left-hint");
  var max = parseInt(btn.getAttribute("data-max"), 10) || 10;
  var base = btn.getAttribute("data-base") || "/deals";

  function picked() {
    return Array.prototype.slice.call(document.querySelectorAll(".js-intro-pick"))
      .filter(function (c) { return c.checked; })
      .map(function (c) { return c.value; });
  }

  function sync() {
    var ids = picked();
    btn.textContent = "딜 소개 (선택 " + ids.length + "개)";
    var ok = ids.length >= 1 && ids.length <= max;
    if (ok) {
      btn.setAttribute("href", base + "?companies=" + ids.join(","));
      btn.removeAttribute("aria-disabled");
    } else {
      btn.removeAttribute("href");
      btn.setAttribute("aria-disabled", "true");
    }
    if (!hint) return;
    hint.textContent = !ids.length
      ? "왼쪽 체크박스로 소개할 기업을 고르세요 (한 번에 " + max + "개까지)"
      : ids.length > max
        ? "한 번에 " + max + "개까지 담을 수 있습니다 — " + (ids.length - max) + "개를 풀어 주세요"
        : "딜 제안 관리에서 받는 분 · 문구를 고르고 미리보기 · 확인 뒤 보냅니다";
  }

  document.addEventListener("change", function (ev) {
    var t = ev.target;
    if (t && t.classList && t.classList.contains("js-intro-pick")) sync();
  });
  // 잠긴 `<a>` 는 `href` 가 없어 어디로도 안 가지만, 눌림도 막아 둔다(딜 소싱 단추와 같다).
  btn.addEventListener("click", function (ev) {
    if (btn.getAttribute("aria-disabled") === "true") ev.preventDefault();
  });
  // 새로고침 · 뒤로 가기로 돌아오면 브라우저가 체크를 되살려 둔다 — 그 상태로 맞춘다.
  sync();
})();
