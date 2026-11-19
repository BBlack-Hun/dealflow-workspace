// 팀원 화면으로 보는 중에 **어느 탭의 [발송] 이 열리는가.**
// (node tests/js/deals_view_as_tab_test.js)
//
// `view_as.js` 는 누르는 순간 `data-send` 값을 읽는다 — "proxy" 면 확인창을 거쳐
// 열고, 아니면 막는다(`view_as_test.js`). 그 값을 탭마다 바꾸는 것이 deals.js 다.
// 서버 허용 목록(`deps.VIEW_AS_SEND_MODES`)과 어긋나면 열린 탭이 흐려지거나, 막힌
// 탭이 확인창까지 띄우고 403 을 받는다. 여는 탭은 딜 소개 · IR 자료 전달(11/19)뿐이다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const OPEN = ["deal", "ir"];

const dom = deals_.run(null, {});
const button = dom.document.getElementById("send-btn");

// 열린 탭에서 막힌 탭으로, 다시 열린 탭으로 — 오가도 앞 탭의 값이 남지 않아야 한다.
["ir", "remind", "deal", "ir_review", "ir", "meeting", "review", "ask", "sourcing", "deal"]
  .forEach(function (mode) {
    deals_.pickMode(dom, mode);
    assert.strictEqual(button.getAttribute("data-send"),
                       OPEN.indexOf(mode) >= 0 ? "proxy" : "",
                       mode + " 탭의 [발송] 표시가 서버 허용 목록과 다르다");
  });

console.log("deals_view_as_tab_test: ok");
