// 딜 소개 — 「내가 아직 소개 안 한 기업만」(#92). (node tests/js/deals_only_unsent_test.js)
//
// 카드의 `data-my-got` 은 **내 딜소개 명단 중 이 기업을 받은 사람 수**다
// (`deal_history.annotate(mine=...)` — 세는 것은 파이썬 쪽 검사가 본다).
// 여기서는 체크를 켜면 한 명이라도 받은 기업이 빠지고, **고른 기업은 그래도
// 보이는지**만 본다(검색 · 45일 숨기기와 같은 규칙).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const A = "가나애그";    // 내 명단 중 3명이 받음
const B = "다라헬스";    // 아무도 안 받음
const C = "마바로보";    // 3명이 받았지만 이미 골라 둠

const dom = deals_.run(null, {
  prepare: function (d) {
    const box = d.document.createElement("input");
    box.setAttribute("id", "only-unsent");
    box.setAttribute("type", "checkbox");
    d.root.appendChild(box);
    deals_.companyBox(d, A).closest(".pick-card").setAttribute("data-my-got", "3");
    deals_.companyBox(d, B).closest(".pick-card").setAttribute("data-my-got", "0");
    deals_.companyBox(d, C).closest(".pick-card").setAttribute("data-my-got", "3");
  }
});
deals_.toggleCompany(dom, C);

function hidden(name) {
  return deals_.companyBox(dom, name).closest(".pick-card").hidden;
}

const box = dom.document.getElementById("only-unsent");
box.checked = true;
box.fire("change");
assert.strictEqual(hidden(A), true, "내가 소개한 기업이 그대로 보인다");
assert.strictEqual(hidden(B), false, "아직 소개 안 한 기업이 숨었다");
assert.strictEqual(hidden(C), false, "고른 기업은 언제나 보여야 한다");

box.checked = false;
box.fire("change");
assert.strictEqual(hidden(A), false, "체크를 풀었는데 다시 안 보인다");

console.log("deals_only_unsent_test: ok");
