// 팀원 화면으로 보는 중(#3) — 발송·예약 단추를 끈다.
//
// 막는 것은 서버다(`deps.no_send_as_member` → 403). 여기는 누르기 **전에**
// 왜 안 되는지 보이게 할 뿐이다: `data-send` 가 붙은 단추·폼을 흐리게 하고
// (app.css), 올리면 사유가 뜨고, 눌러도 아무 데도 가지 않는다.
// 페이지 스크립트보다 먼저 듣도록 **잡는 단계**(capture)에서 끊는다.
//
// `data-send="proxy"`(방 찾기 · 딜 소개 발송 — 10/30)는 끄지 않고, **어느 계정 PC
// 카톡으로 나가는지** 확인창을 먼저 띄운다. 값은 누르는 순간 읽는다 — 딜 제안
// 관리는 탭을 바꿀 때 [발송] 단추의 값을 바꾼다(`deals.js`).
(function () {
  var note = document.body.getAttribute("data-view-as-note");
  if (!note) return;
  var sendNote = document.body.getAttribute("data-view-as-send") || "";
  function stop(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
  function gate(e, el) {
    if (el.getAttribute("data-send") === "proxy") {
      if (!confirm(sendNote + "\n계속할까요?")) stop(e);
      return;
    }
    stop(e);
    alert(note);
  }
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-send]");
    // 폼은 제출만 끊는다 — 안의 칸을 누르는 것까지 막을 까닭은 없다.
    if (el && el.tagName !== "FORM") gate(e, el);
  }, true);
  document.addEventListener("submit", function (e) {
    var el = e.target.closest("[data-send]");
    if (el) gate(e, el);
  }, true);
  document.querySelectorAll("[data-send]").forEach(function (el) {
    if (el.getAttribute("data-send") === "proxy") return;
    el.title = note;
    el.setAttribute("aria-disabled", "true");
  });
})();
