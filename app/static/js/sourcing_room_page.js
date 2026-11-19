// 딜 소싱 카톡방 찾기 화면(`sourcing_rooms.html`) — **체크한 분만** 찾기.
// (node tests/js/sourcing_room_page_test.js)
//
// 딜 소싱 화면의 [카톡방 후보 찾기 (선택 N명)]과 같은 방식이다: 체크한 줄 번호를 폼의
// `ids` 에 실어 같은 주소(`/sourcing/rooms/search`)로 보낸다. 무엇을 찾을 수 있는지는
// 서버가 정한다 — 찾는 중이거나 찾을 대상이 아닌 줄은 체크 칸이 잠겨서 오고
// (`sourcing_rooms.board` 의 `findable`), 서버가 한 번 더 거른다(`sourcing_rooms.targets`).
(function () {
  var form = document.getElementById("room-pick-form");
  if (!form) return;
  var btn = form.querySelector("button");
  var ids = form.querySelector('input[name="ids"]');
  var all = document.getElementById("room-pick-all");

  function boxes() {
    return Array.prototype.filter.call(document.querySelectorAll(".js-room-pick"),
                                       function (b) { return !b.disabled; });
  }
  function sync() {
    var open = boxes();
    var on = open.filter(function (b) { return b.checked; });
    ids.value = on.map(function (b) { return b.value; }).join(",");
    btn.textContent = "체크한 분 찾기 (" + on.length + "명)";
    btn.disabled = !on.length;
    if (all) all.checked = on.length > 0 && on.length === open.length;
  }

  document.addEventListener("change", function (e) {
    var t = e.target;
    if (all && t === all) boxes().forEach(function (b) { b.checked = all.checked; });
    else if (!t || !t.classList || !t.classList.contains("js-room-pick")) return;
    sync();
  });
  sync();   // 뒤로 가기로 돌아오면 브라우저가 체크를 되살린다 — 그 셈으로 시작한다
})();
