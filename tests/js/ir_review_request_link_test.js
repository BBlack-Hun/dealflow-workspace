// IR 진행 관리 `전달한 자료` 의 투자사명은 이제 **`IR 자료 검토 요청`** 탭으로 연다(#79).
// 주소를 받은 쪽(`deals.js`)이 그 방식 · 그 담당자로 여는지 본다 — 미팅 요청은 줄의
// [미팅 요청] 단추가 여는 `?mode=meeting`(ir_sent_meeting_link_test.js)이다.
//
//   node tests/js/ir_review_request_link_test.js
"use strict";
const assert = require("assert");
const deals_ = require("./_deals_dom.js");

const dom = deals_.run(null, { search: "?mode=ir_review&contacts=2" });
assert.deepStrictEqual(deals_.checkedNames(dom), ["나담당"],
  "링크로 넘어온 담당자가 안 골라졌다: " + deals_.checkedNames(dom));
const active = Array.prototype.slice
  .call(dom.document.querySelectorAll(".mode-tab"))
  .filter(function (b) { return b.classList.contains("active"); })
  .map(function (b) { return b.getAttribute("data-mode"); });
assert.deepStrictEqual(active, ["ir_review"], "검토 요청 방식으로 안 열렸다: " + active);
// 기업 목록 없이 문구만 나간다 — 기업 칸이 흐려진다(`MODES_WITH_COMPANIES` 와 짝).
assert.ok(dom.companyPanel.classList.contains("dimmed"), "검토 요청인데 기업 칸이 살아 있다");

console.log("ir_review_request_link_test.js OK");
