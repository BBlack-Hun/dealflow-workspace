// 팀원 화면으로 보는 중(#3) — 발송·예약·방 확인 단추를 끈다.
//
// 막는 것은 서버다(`deps.no_send_as_member` → 403). 여기는 누르기 **전에**
// 왜 안 되는지 보이게 할 뿐이다: `data-send` 가 붙은 단추·폼을 흐리게 하고
// (app.css), 올리면 사유가 뜨고, 눌러도 아무 데도 가지 않는다.
// 페이지 스크립트보다 먼저 듣도록 **잡는 단계**(capture)에서 끊는다.
(function () {
  var note = document.body.getAttribute("data-view-as-note");
  if (!note) return;
  function stop(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
    alert(note);
  }
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-send]");
    // 폼은 제출만 끊는다 — 안의 칸을 누르는 것까지 막을 까닭은 없다.
    if (el && el.tagName !== "FORM") stop(e);
  }, true);
  document.addEventListener("submit", function (e) {
    if (e.target.closest("[data-send]")) stop(e);
  }, true);
  document.querySelectorAll("[data-send]").forEach(function (el) {
    el.title = note;
    el.setAttribute("aria-disabled", "true");
  });
})();
