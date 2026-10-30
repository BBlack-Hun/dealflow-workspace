// 스타트업 월간 발송 — **그 달 글을 이미 받은 기업**을 다시 켤 때 한 번 묻는다.
//
// 그 줄의 체크칸은 `data-sent-this-month`(보낸 날)를 달고 꺼진 채로 선다. 전체 선택은 켤 때
// 그 줄을 건너뛴다. 사람이 직접 켜면 확인 창을 띄우고, [확인] 이면 같은 줄의
// `resend_ids` 를 살려 함께 보낸다 — 서버는 그 값이 없는 이미 받은 기업을 뺀다
// (`routers/startup_send.make_draft`). [취소] 면 도로 끄고 change 를 다시 알린다 —
// 전체 선택 머리가 그것을 듣고 다시 센다(꺼진 칸이라 다시 묻지는 않는다).
(function () {
  "use strict";
  document.addEventListener("change", function (ev) {
    var box = ev.target;
    if (!box || !box.hasAttribute || !box.hasAttribute("data-sent-this-month")) return;
    var row = box.closest("tr");
    var ok = row && row.querySelector('input[name="resend_ids"]');
    if (!ok) return;
    if (box.checked && !window.confirm(
        "이 기업은 이번 달 월간 글을 이미 받았습니다(" +
        box.getAttribute("data-sent-this-month") + ").\n같은 달 글을 다시 보낼까요?")) {
      box.checked = false;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    }
    ok.disabled = !box.checked;
  });
})();
