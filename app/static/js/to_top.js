// 오른쪽 아래 '맨 위로' 단추(base.html 의 `#to-top`). (node tests/js/to_top_test.js)
//
// ## 스크롤이 두 군데서 일어난다
//
// 창, 그리고 넓은 표 상자(`.table-wrap.wide`). 표 상자는 화면 높이로 잘려
// **안에서 따로 세로로 민다**(까닭은 app.css · table_fit.js). 창만 보면 표 안에서
// 수백 줄을 내려가도 단추가 안 뜨고, 창만 올리면 표는 아래에 그대로 있다.
// 그래서 둘 다 보고, 누르면 둘 다 올린다.
//
// `scroll` 은 버블링하지 않는다 — 표 상자 안의 스크롤은 문서까지 안 올라온다.
// 문서에서 **잡는 단계**(capture)로 들으면 창이든 표 상자든 한 자리에서 듣는다.
//
// ## 세로만 올린다
//
// 넓은 표는 가로로 1,900px 넘게 밀어 두고 본다. 맨 위로 가면서 가로까지 0 으로
// 돌리면 보던 칸을 잃는다 — `scrollLeft` 는 건드리지 않는다.
//
// 스크롤 자리를 **읽기만** 하고 쓰는 것은 누를 때뿐이다. 다시 그린 뒤 표 자리를
// 되살리는 `contacts.js`(restoreScroll)와 부딪히지 않는다.
"use strict";

(function (global) {
  // 이만큼 내려가야 단추가 선다. 맨 위 근처에서는 올라갈 데가 없는데 단추가
  // 표의 오른쪽 아래 칸만 가린다.
  var SHOW_AT = 300;
  var WRAPS = ".table-wrap.wide";

  function scrolledDown(win, doc) {
    if ((win.pageYOffset || 0) > SHOW_AT) return true;
    var wraps = doc.querySelectorAll(WRAPS);
    for (var i = 0; i < wraps.length; i += 1) {
      if ((wraps[i].scrollTop || 0) > SHOW_AT) return true;
    }
    return false;
  }

  function toTop(win, doc) {
    // 표 상자가 여럿인 화면(IR 발송)도 있다 — 다 올린다. 이미 맨 위면 아무 일 없다.
    var wraps = doc.querySelectorAll(WRAPS);
    for (var i = 0; i < wraps.length; i += 1) wraps[i].scrollTop = 0;
    // `scrollTo(0, 0)` 이면 창의 가로 자리까지 돌아간다.
    win.scrollTo(win.pageXOffset || 0, 0);
  }

  function init(win, doc) {
    var btn = doc.getElementById("to-top");
    if (!btn) return null;

    var pending = false;
    function update() {
      pending = false;
      btn.hidden = !scrolledDown(win, doc);
    }
    // 스크롤은 한 프레임에 여러 번 온다 — 프레임마다 한 번만 잰다.
    function schedule() {
      if (pending) return;
      pending = true;
      if (typeof win.requestAnimationFrame === "function") win.requestAnimationFrame(update);
      else setTimeout(update, 0);
    }

    doc.addEventListener("scroll", schedule, true);
    btn.addEventListener("click", function () { toTop(win, doc); update(); });
    // 브라우저가 자리를 되살린 채 열리는 화면(뒤로 가기 · 새로고침)이 있다.
    update();
    return { update: update };
  }

  if (global.document && global.addEventListener) init(global, global.document);

  // 검사가 이 셈을 그대로 돌려 볼 수 있게 내보낸다.
  if (typeof module === "object" && module.exports) {
    module.exports = { init: init, SHOW_AT: SHOW_AT, WRAPS: WRAPS };
  }
})(typeof window !== "undefined" ? window : globalThis);
