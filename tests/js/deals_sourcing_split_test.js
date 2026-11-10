// 딜 제안 관리 › [딜 소싱 제안]의 시리즈 A 두 칩 — `검토가능 심사역` · `참여 심사역` (#210).
// (node tests/js/deals_sourcing_split_test.js)
//
// 11/10 팀원 요청: 딜 소싱 화면의 `검토가능 81 · 참여 26` 이 여기서도 같은 두 묶음 · 같은 수로
// 서고, 검토가능을 누르면 참여 안내 (처음) 문구로, 참여를 누르면 딜 발송 요청 문구로 그분들을
// 고른다. 못 박는 것:
//   ① 칩 수 = 그 묶음 인원 — 고른 글 · 이 달 딜 받음과 상관없다
//   ② 누르면 문구가 바뀌고 그 묶음의 뜬 카드만 고른다(다른 체크는 푼다)
//   ③ 리마인드의 이 달 딜 받음 제외 · [포함]을 그대로 따른다
//   ④ [보낼 문구]를 손으로 바꾸면 켜진 칩도 따라 옮긴다
//   ⑤ 명단을 다시 읽으면 수가 따라 바뀐다
//   ⑥ 보내지는 않는다 — `/api/deals/send` 를 부르지 않는다
//
// 이름은 전부 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const SA = deals_.SHARE_BUCKET;
// 가소싱(101 · 시리즈 A) — 제안 대기중(참여 안내만). 나소싱(102 · M&A) — 참여.
// 다소싱(103 · 시리즈 A) — 참여, 이 달 딜 받음.
let STATE = {
  rows: [
    { id: 101, assignee: "가담당", received: false, invite_only: true },
    { id: 102, assignee: "나담당", received: false },
    { id: 103, assignee: "가담당", received: true }
  ],
  assignees: [{ name: "가담당", count: 2 }, { name: "나담당", count: 1 }]
};

const fetch = deals_.fakeFetch([], null, { "/api/sourcing/state": function () { return STATE; } });
const dom = deals_.run(null, { fetch: fetch, setTimeout: function (fn) { fn(); return 0; } });
deals_.pickMode(dom, "sourcing");

const doc = dom.document;
function split(kind) { return doc.querySelector('#bucket-filter .chip[data-split="' + kind + '"]'); }
function count(kind) { return Number(split(kind).querySelector("b").textContent); }
function topic() {
  const on = doc.querySelectorAll("#sourcing-topic .chip").filter(function (c) {
    return c.classList.contains("active");
  });
  assert.strictEqual(on.length, 1, "켜진 문구 칩이 하나가 아니다");
  return on[0].getAttribute("data-value");
}
function checked() {
  return dom.sourcingCards.filter(function (c) { return c.querySelector(".contact-cb").checked; })
    .map(function (c) { return c.querySelector(".contact-cb").getAttribute("data-name"); }).sort();
}
function box(name) {
  return dom.sourcingCards.map(function (c) { return c.querySelector(".contact-cb"); })
    .filter(function (cb) { return cb.getAttribute("data-name") === name; })[0];
}
function pickTopic(value) {
  doc.querySelector('#sourcing-topic .chip[data-value="' + value + '"]').fire("click");
}

// --- ① 칩 수 = 묶음 인원 -------------------------------------------------------
assert.strictEqual(count("invite"), 1, "검토가능 수가 틀렸다");
assert.strictEqual(count("joined"), 1, "참여 수가 틀렸다(이 달 딜 받음도 참여다)");
pickTopic("sourcing_remind");
assert.strictEqual(count("invite"), 1, "문구를 바꿨더니 검토가능 수가 흔들렸다");
assert.strictEqual(count("joined"), 1, "문구를 바꿨더니 참여 수가 흔들렸다");
pickTopic("sourcing_intro");

// --- ② 검토가능을 누르면 참여 안내 문구로 그분들을 고른다 ---------------------------
pickTopic("sourcing_remind");
box("나소싱").checked = true;              // 다른 갈래에서 골라 둔 분 — 칩을 누르면 풀린다
box("나소싱").fire("change");
split("invite").fire("click");
assert.strictEqual(topic(), "sourcing_intro", "검토가능을 눌렀는데 참여 안내 문구가 아니다");
assert.deepStrictEqual(checked(), ["가소싱"], "검토가능을 눌렀는데 그분들만 골라지지 않았다");
assert.ok(split("invite").classList.contains("active"));
assert.ok(!split("joined").classList.contains("active"));

// --- ③ 참여를 누르면 딜 발송 요청 문구 — 이 달 딜 받음은 기본으로 뺀다 --------------
split("joined").fire("click");
assert.strictEqual(topic(), "sourcing_remind", "참여를 눌렀는데 딜 발송 요청 문구가 아니다");
assert.deepStrictEqual(checked(), [], "이 달 딜 받음인 분이 골라졌다");
assert.strictEqual(doc.getElementById("received-note").hidden, false, "딜 받음 제외를 말하지 않는다");
const include = doc.getElementById("include-received");
include.checked = true;
include.fire("change");
split("joined").fire("click");
assert.deepStrictEqual(checked(), ["다소싱"], "[이번 달 딜 받음 포함]인데 그분이 안 골라졌다");
assert.ok(split("joined").classList.contains("active"));

// --- ④ 문구를 손으로 바꾸면 켜진 칩도 옮긴다 ------------------------------------------
pickTopic("sourcing_intro");
assert.ok(split("invite").classList.contains("active"), "참여 안내로 바꿨는데 참여 칩이 켜진 채다");
assert.ok(!split("joined").classList.contains("active"));
assert.deepStrictEqual(checked(), [], "참여 안내로 바꿨는데 참여 분 체크가 남았다");

// --- ⑤ 명단을 다시 읽으면 수가 따라 바뀐다 ------------------------------------------
// 가소싱이 그 사이 `참여` 가 됐다(딜 소싱 화면에서 고침) — 창으로 돌아오면 다시 읽는다.
STATE = { rows: [{ id: 101, assignee: "가담당", received: false },
                 { id: 102, assignee: "나담당", received: false },
                 { id: 103, assignee: "가담당", received: true }],
          assignees: STATE.assignees };
dom.root.fire("visibilitychange");
assert.strictEqual(count("invite"), 0, "다시 읽었는데 검토가능 수가 그대로다");
assert.strictEqual(count("joined"), 2, "다시 읽었는데 참여 수가 그대로다");

// --- ⑥ 보내지는 않는다 ---------------------------------------------------------------
assert.ok(!fetch.calls.some(function (c) { return c.url === "/api/deals/send"; }),
          "칩을 눌렀는데 보내기를 불렀다");

console.log("deals_sourcing_split_test: ok");
