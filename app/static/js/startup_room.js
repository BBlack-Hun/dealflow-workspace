/* 대표 카톡방 맞추기 — **후보를 누르면 그 줄의 칸에 넣는다.** 그게 전부다.
 * (node tests/js/startup_room_test.js)
 *
 * ## 여기서 판단하지 않는다  ★
 *
 * 어느 후보가 그 회사 것인지, 초안이 맞는지는 **서버가 정해서 보내 준다**
 * (`services/room_match.has_company_name` · `draft`). 여기서 회사명을 다시
 * 견주면 같은 규칙이 파이썬과 자바스크립트 두 벌이 되고, 한쪽만 고쳐지는
 * 날 화면이 도드라지게 세운 후보와 서버가 맞다고 본 후보가 갈린다.
 * 그래서 이 파일은 **글자를 옮기는 일만** 한다.
 *
 * ## 저절로 넣지 않는다  ★
 *
 * 후보가 하나뿐인 줄에도 자동으로 채우지 않는다. 채워 두면 사람은 이미
 * 확인된 값으로 읽고 그대로 저장한다 — 회사명이 든 방이 꼭 대표와의 방인
 * 것은 아니라서, 그 한 번이 엉뚱한 방으로 가는 발송이 된다.
 *
 * ## 이 파일이 없어도 표는 쓸 수 있다
 *
 * 후보는 눌러서 넣는 **단추**이기도 하고 눈으로 읽는 **글자**이기도 하다.
 * 스크립트가 안 돌면 보고 옮겨 적으면 된다 — 저장은 평범한 폼 전송이다.
 */
(function () {
  "use strict";

  var form = document.getElementById("room-match");
  if (!form) return;

  // 줄 안에서 칸을 찾는다. `closest("tr")` 로 그 줄에 갇히는 것이 핵심이다 —
  // 표 전체에서 첫 칸을 찾으면 어느 줄을 눌러도 맨 윗줄에 들어간다.
  function inputOf(button) {
    var row = button.closest("tr");
    return row ? row.querySelector(".room-input") : null;
  }

  // 한 자리에서 위임으로 받는다. 줄마다 따로 걸면 수십 개가 매달리고,
  // 줄이 다시 그려질 때 걸어 둔 것이 떨어진다.
  form.addEventListener("click", function (e) {
    var button = e.target.closest(".room-pick");
    if (!button) return;
    // 단추는 `type="button"` 이지만 그것만 믿지 않는다 — 폼 안이라 하나라도
    // 빠뜨리면 **후보를 누른 것이 저장으로** 이어진다.
    e.preventDefault();

    var input = inputOf(button);
    if (!input) return;
    input.value = button.getAttribute("data-room") || "";
    // 넣은 자리에 초점을 둔다. 띄어쓰기 하나를 고쳐야 하는 경우가 흔한데
    // (카톡 제목과 우리가 아는 회사명이 다르게 띄어져 있다), 초점이 없으면
    // 사람이 그 칸을 다시 찾아 눌러야 한다.
    if (typeof input.focus === "function") input.focus();
  });
})();
