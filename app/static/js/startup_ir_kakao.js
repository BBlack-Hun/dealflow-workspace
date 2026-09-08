/* IR 요청 투자사 카톡 문구 — [문구 복사] 하나를 붙이는 자리.
 *
 * **복사하는 코드가 여기 없다.** `ir_attach_list.js` 의 `IrAttach.copyText` 가
 * 클립보드·되돌림(execCommand)·`Ctrl/⌘+C 로 복사하세요` 안내·단추 글자
 * 되돌리기를 전부 한다. 여기서 다시 적으면 세 화면의 복사가 조금씩 달라지고,
 * 달라진 것은 누가 눌러 보기 전까지 아무도 모른다.
 */
(function () {
  "use strict";

  var btn = document.getElementById("ir-kakao-copy");
  var body = document.getElementById("ir-kakao-message");
  // 문구가 없는 달이면 화면에 둘 다 없다. 공용 한 벌이 안 실렸어도 조용히 만다 —
  // 여기서 제 손으로 복사하는 길을 만들지 않는다.
  if (!btn || !body || !window.IrAttach) return;

  btn.addEventListener("click", function () {
    window.IrAttach.copyText(body, btn);
  });
}());
