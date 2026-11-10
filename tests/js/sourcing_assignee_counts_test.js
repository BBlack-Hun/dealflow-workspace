// 딜 소싱 제안의 [담당] 칩 숫자 = **지금 고른 문구에서 뜨는 카드 수**.
// (node tests/js/sourcing_assignee_counts_test.js)
//
// 서버는 어느 글이든 받는 분(참여 · 제안 대기중 · 물어보는 중)을 다 세어 칩을 세운다
// (`sourcing.assignee_chips`). 그런데 리마인드 · Series A 딜 공유는 `참여` 카드만,
// 참여 안내(처음)는 제안 대기중 · 물어보는 중 카드만 뜬다 — 칩 55 인데 카드 13장이었다.
//
//   ① 문구를 바꾸면 다시 센다 — 칩을 누르면 그 수만큼 카드가 뜬다
//   ② 리마인드의 [이번 달 딜 받음 포함]을 켜고 끄는 것도 따라온다
//   ③ 0 인 칩은 숨는다(서버도 0 인 칩은 안 세운다) — 고르던 칩이 숨으면 [전체]로
//
// 이름은 전부 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const STATE_URL = "/api/sourcing/state";
// 가소싱(가담당) — 제안 대기중: 참여 안내에만 뜬다.
// 나소싱(나담당) · 다소싱(가담당, 이 달 딜 받음) — 참여: 다른 글에만 뜬다.
const STATE = {
  rows: [
    { id: 101, assignee: "가담당", received: false, invite_only: true },
    { id: 102, assignee: "나담당", received: false },
    { id: 103, assignee: "가담당", received: true }
  ],
  assignees: [{ name: "가담당", count: 2 }, { name: "나담당", count: 1 }]
};

function setup() {
  const gets = {};
  gets[STATE_URL] = STATE;
  const fetch = deals_.fakeFetch([], null, gets);
  const dom = deals_.run(null, { fetch: fetch, setTimeout: function (fn) { fn(); return 0; } });
  deals_.pickMode(dom, "sourcing");
  return dom;
}

function chip(dom, name) {
  return dom.document.querySelector('#assignee-filter .chip[data-value="' + name + '"]');
}

// 보이는 칩 → 숫자. 숨은 칩은 빠진다.
function counts(dom) {
  const out = {};
  dom.document.querySelectorAll("#assignee-filter .chip").slice(1).forEach(function (c) {
    if (!c.hidden) out[c.getAttribute("data-value")] = Number(/<b>(\d+)<\/b>/.exec(c.innerHTML)[1]);
  });
  return out;
}

function shown(dom) {
  return dom.sourcingCards.filter(function (c) { return !c.hidden; }).length;
}

function pickTopic(dom, value) {
  dom.document.querySelector('#sourcing-topic .chip[data-value="' + value + '"]').fire("click");
}

// 칩마다 눌러 보면 그 수만큼 카드가 뜬다 — 칩 숫자가 곧 화면의 카드 수다.
function assertChipsMatchCards(dom, label) {
  const got = counts(dom);
  Object.keys(got).forEach(function (name) {
    chip(dom, name).fire("click");
    assert.strictEqual(shown(dom), got[name], label + ": " + name + " 칩 수와 뜬 카드 수가 다르다");
  });
  chip(dom, "").fire("click");
}

// --- ① 문구마다 다시 센다 ----------------------------------------------------
const dom = setup();
assert.deepStrictEqual(counts(dom), { "가담당": 1 },
                       "참여 안내(처음)인데 참여 카드까지 셌다(또는 0 인 칩이 보인다)");
assertChipsMatchCards(dom, "참여 안내");

pickTopic(dom, "sourcing_remind");          // 참여만 · 이 달 딜 받음은 기본으로 뺀다
assert.deepStrictEqual(counts(dom), { "나담당": 1 }, "리마인드 칩 수가 뜬 카드와 다르다");
assertChipsMatchCards(dom, "딜 발송 요청");

// --- ② [이번 달 딜 받음 포함] ------------------------------------------------
const include = dom.document.getElementById("include-received");
include.checked = true;
include.fire("change");
assert.deepStrictEqual(counts(dom), { "가담당": 1, "나담당": 1 }, "딜 받음 포함을 켰는데 안 늘었다");
assertChipsMatchCards(dom, "리마인드 · 딜 받음 포함");
include.checked = false;
include.fire("change");

pickTopic(dom, "sourcing_deal_share");      // 시리즈 A 갈래의 참여 분만
assert.deepStrictEqual(counts(dom), { "가담당": 1 }, "Series A 딜 공유 칩 수가 뜬 카드와 다르다");
assertChipsMatchCards(dom, "Series A 딜 공유");

// --- ③ 고르던 칩이 0 이 되면 [전체]로 -----------------------------------------
pickTopic(dom, "sourcing_intro");
chip(dom, "가담당").fire("click");
assert.strictEqual(shown(dom), 1);
pickTopic(dom, "sourcing_remind");          // 가담당은 이 글에 뜰 카드가 없다
assert.strictEqual(chip(dom, "가담당").hidden, true, "0 인 칩이 남았다");
assert.ok(chip(dom, "").classList.contains("active"), "숨은 칩이 켜진 채다 — [전체]로 안 돌아갔다");
assert.strictEqual(shown(dom), 1, "[전체]로 돌아갔는데 리마인드 카드가 안 보인다");
// 서버가 센 값(`data-count`)은 그대로다 — 다시 읽을 때 바뀌었는지 견주는 값이다.
assert.strictEqual(chip(dom, "가담당").getAttribute("data-count"), "2");

// --- ④ [갈래] 칩 수도 고른 글을 따른다(i128) ---------------------------------
// 시리즈 A 갈래 = 가소싱(제안 대기중) · 다소싱(참여, 이 달 딜 받음), M&A = 나소싱(참여).
// 시리즈 A 는 칩 둘(#210 — `검토가능 심사역` · `참여 심사역`)이고, 그 둘은 고른 글 · 이 달
// 딜 받음과 상관없이 **묶음 인원**이다(딜 소싱 화면의 그 탭 칩과 같은 수 — `splitCount`).
function bucketCounts(dom) {
  const out = {};
  dom.document.querySelectorAll("#bucket-filter .chip").forEach(function (c) {
    const key = (c.getAttribute("data-value") || "전체") +
      (c.getAttribute("data-split") ? ":" + c.getAttribute("data-split") : "");
    out[key] = Number(c.querySelector("b").textContent);
  });
  return out;
}
const SA = "시리즈 A 이상 딜소싱 참여 심사역";
const SPLIT = { [SA + ":invite"]: 1, [SA + ":joined"]: 1 };
pickTopic(dom, "sourcing_intro");
assert.deepStrictEqual(bucketCounts(dom), Object.assign({ "전체": 1, "M&A 찾는 투자사": 0 }, SPLIT),
                       "참여 안내인데 갈래 칩이 참여 카드까지 셌다");
pickTopic(dom, "sourcing_remind");
assert.deepStrictEqual(bucketCounts(dom), Object.assign({ "전체": 1, "M&A 찾는 투자사": 1 }, SPLIT),
                       "딜 발송 요청 갈래 칩 수가 뜬 카드와 다르다");
include.checked = true;
include.fire("change");
assert.deepStrictEqual(bucketCounts(dom), Object.assign({ "전체": 2, "M&A 찾는 투자사": 1 }, SPLIT));
// 0 인 갈래 칩은 숨기지 않는다 — 갈래 칩은 문구도 고른다.
assert.ok(dom.document.querySelectorAll("#bucket-filter .chip").every(function (c) { return !c.hidden; }));

console.log("sourcing_assignee_counts_test: ok");
