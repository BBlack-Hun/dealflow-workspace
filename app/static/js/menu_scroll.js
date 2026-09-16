// 눕힌 줄에서 **지금 있는 자리**를 보이게 한다. (node tests/js/menu_scroll_test.js)
//
// ## 무엇이 없었는가
//
// 좁은 폭에서 좌측 메뉴는 가로로 눕고(app.css 의 `@media (max-width: 1080px)`
// `.menu { flex-direction: row; overflow-x: auto }`), 명단 탭 줄도 넘치면 가로로
// 민다(`@media (max-width: 720px)` 의 `.sheet-tabs`). 눕히는 것까지는 CSS 가
// 하는데, 눕힌 줄은 늘 **맨 왼쪽에서** 시작한다 — 지금 보고 있는 화면이
// 오른쪽에 적혀 있으면 그 표시가 화면 밖이다.
//
// 390px 아이폰에서 잰 값. 줄의 보이는 폭은 390px 이고, 아래는 활성 항목이
// 그 줄 안에서 차지하는 자리다(왼쪽 끝에서부터):
//
//     주간 업무          84–177    보인다
//     딜 제안 관리      181–265    보인다
//     투자사 관리 현황  269–376    보인다
//     스타트업          380–447    ← 밖
//     IR 기업 현황      451–535    ← 밖
//     딜 진행 관리      602–687    ← 밖
//     투자컨설턴트      779–868    ← 밖
//     업무 보고         872–942    ← 밖
//     팀 현황           946–1005   ← 밖
//
// **열 화면 중 여섯에서 어느 것이 켜져 있는지 안 보인다.** 게다가 여섯 화면의
// 메뉴 줄은 첫 세 칸만 보이므로 서로 똑같이 생겼다 — 화면을 옮겨도 머리가
// 안 바뀐 것처럼 보인다. 1440px 에서는 메뉴가 세로라 열 화면 모두 활성 항목이
// 보인다(재서 확인했다). **넓은 화면에만 있는 것**이라 여기서 채운다.
//
// 명단 탭도 같은 자리다. 투자컨설턴트의 세 번째 탭을 고르면 그 탭이 262–426
// 인데 줄은 362px 이라, 고른 탭이 안 보인다. 명단이 늘수록 더 뒤로 간다.
//
// ## 왜 `scrollIntoView` 가 아닌가
//
// 그것은 **조상까지 같이 민다.** 줄 하나를 맞추자고 페이지를 세로로 밀면,
// 화면을 열자마자 본문이 내려가 있어 무엇이 움직였는지 알 수가 없다.
// 여기서 건드리는 것은 그 줄의 `scrollLeft` 하나뿐이다.
//
// ## 왜 폭을 여기서 다시 재지 않는가
//
// `table_fit.js` 와 같은 이유다. 화면 크기 경계는 CSS 한 곳에 있고, 여기서는
// **줄이 실제로 가로로 밀리는가**(`scrollWidth > clientWidth`)만 본다. 넓은
// 화면에서 메뉴는 세로라 이 값이 같아서, 아무 일도 하지 않는다.
"use strict";

(function (global) {
  // 줄 끝에 딱 붙이지 않는다 — 옆에 더 있다는 것이 보여야 민다는 것을 안다.
  var EDGE = 12;

  // 눕는 줄과 그 줄에서 '지금 여기' 를 뜻하는 표시.
  // 둘 다 `active` 를 쓰지만 **선택자를 한데 묶지 않는다** — 한쪽 이름이
  // 바뀌면 다른 쪽까지 조용히 안 걸리게 된다.
  var STRIPS = [
    [".menu", ".menu-item.active"],
    [".sheet-tabs", ".sheet-tab.active"],
  ];

  function pullIntoView(box, activeSelector) {
    if (!box) return false;
    var active = box.querySelector(activeSelector);
    if (!active) return false;
    // **가로로 밀리는 줄일 때만.** 안 밀리는 줄에서 `scrollLeft` 를 건드리면
    // 아무 일도 안 하지만, 그 사실이 코드에 안 적혀 있으면 다음 사람이
    // "넓은 화면에서도 도는 것" 으로 읽는다.
    if (box.scrollWidth <= box.clientWidth) return false;
    var br = box.getBoundingClientRect();
    var ar = active.getBoundingClientRect();
    // 오른쪽으로 넘쳤으면 넘친 만큼만, 왼쪽으로 넘쳤으면 모자란 만큼만.
    // (필터 창을 화면 안으로 끌어당기는 `filters.js` 의 `clampIntoView` 와
    //  같은 셈이다 — 그쪽은 창을 옮기고 이쪽은 줄을 민다.)
    var over = ar.right - (br.right - EDGE);
    if (over > 0) { box.scrollLeft += over; return true; }
    var under = (br.left + EDGE) - ar.left;
    if (under > 0) { box.scrollLeft -= under; return true; }
    return false;
  }

  function pullAll(doc) {
    var d = doc || (global.document);
    if (!d) return 0;
    var moved = 0;
    for (var i = 0; i < STRIPS.length; i += 1) {
      var boxes = d.querySelectorAll(STRIPS[i][0]);
      for (var j = 0; j < boxes.length; j += 1) {
        if (pullIntoView(boxes[j], STRIPS[i][1])) moved += 1;
      }
    }
    return moved;
  }

  if (global.document && global.addEventListener) {
    pullAll();
    // 폰을 돌리면 폭이 바뀐다 — 세로로 세웠을 때 밖이던 것이 가로에서는
    // 안이고, 그 반대도 있다.
    global.addEventListener("resize", function () { pullAll(); });
    // 글꼴이 늦게 오면 항목 폭이 한 번 더 바뀐다(`table_fit.js` 와 같은 자리).
    if (global.document.fonts && global.document.fonts.ready
        && global.document.fonts.ready.then) {
      global.document.fonts.ready.then(function () { pullAll(); });
    }
  }

  // 검사가 이 셈을 그대로 돌려 볼 수 있게 내보낸다.
  if (typeof module === "object" && module.exports) {
    module.exports = { pullAll: pullAll, pullIntoView: pullIntoView,
                       EDGE: EDGE, STRIPS: STRIPS };
  }
})(typeof window !== "undefined" ? window : globalThis);
