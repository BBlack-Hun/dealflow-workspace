// 딜 제안 관리를 딜 소싱 화면의 [검토 가능 심사역 참여 안내] 링크로 열면
// (`?mode=sourcing&topic=sourcing_intro&contacts=…`) — 그 글 · 그분들이 미리 골라지는가.
// (node tests/js/deals_sourcing_invite_link_test.js)
//
//   ① [딜 소싱 제안] 탭 · [보낼 문구 › 검토 가능 심사역 참여 안내]로 열린다
//   ② 넘겨받은 분 중 참여 안내 카드(`data-invite-only="1"`)만 켠다 — 참여 중인 분은
//      켜지 않고 몇 명인지 말한다. 같은 번호의 투자사 담당자는 켜지 않는다
//   ③ 미리보기가 그 글(`topic: sourcing_intro`) · 그분들로 묻는다. 보내지는 않는다
//   ④ 다른 글로 열린 화면에서 온 것이 아니어도 — 리마인드 주소는 지금처럼 리마인드
//
// 이름은 전부 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

function now(fn) { fn(); return 0; }

// 가소싱(101 · 시리즈 A) — 제안 대기중(참여 안내만). 나소싱(102 · M&A) · 다소싱(103) — 참여.
function invitePrepare(dom) {
  dom.sourcingCards.forEach(function (card) {
    const id = card.querySelector(".contact-cb").value;
    card.setAttribute("data-invite-only", id === "101" ? "1" : "0");
  });
}

function open(search) {
  const fetch = deals_.fakeFetch([], null, {});
  const dom = deals_.run(null, { fetch: fetch, setTimeout: now, search: search,
                                 prepare: invitePrepare });
  return { dom: dom, fetch: fetch };
}

function topic(dom) {
  const on = dom.document.querySelectorAll("#sourcing-topic .chip").filter(function (c) {
    return c.classList.contains("active");
  });
  return on.map(function (c) { return c.getAttribute("data-value"); });
}
function checkedSourcing(dom) {
  return dom.sourcingCards.filter(function (c) { return c.querySelector(".contact-cb").checked; })
    .map(function (c) { return c.querySelector(".contact-cb").value; });
}
function previews(fetch) {
  return fetch.calls.filter(function (c) { return c.url === "/api/deals/preview"; });
}

// --- ①②③ 참여 안내 링크 -----------------------------------------------------------
{
  // 1 은 투자사 담당자 번호와 같은 숫자다 — 그 목록에 켜지면 안 된다.
  const t = open("?mode=sourcing&topic=sourcing_intro&contacts=101,102,1");
  assert.deepStrictEqual(topic(t.dom), ["sourcing_intro"],
                         "[검토 가능 심사역 참여 안내]로 열리지 않았다");
  assert.deepStrictEqual(checkedSourcing(t.dom), ["101"],
                         "참여 안내 대상만 골라져야 한다(참여 중인 분은 안 켠다)");
  assert.strictEqual(t.dom.cards[0].querySelector(".contact-cb").checked, false,
                     "딜 소싱 번호로 투자사 담당자가 켜졌다 — 다른 탭으로 가면 그 분께 나간다");
  const warn = t.dom.document.getElementById("send-warnings").innerHTML;
  assert.ok(/딜 소싱 대상 2명은 고르지 않았습니다/.test(warn), warn);
  const last = previews(t.fetch).pop();
  assert.ok(last, "미리보기를 묻지 않았다");
  assert.strictEqual(last.body.mode, "sourcing");
  assert.strictEqual(last.body.topic, "sourcing_intro");
  assert.deepStrictEqual(last.body.contact_ids, [101]);
  assert.strictEqual(t.fetch.calls.filter(function (c) { return c.url === "/api/deals/send"; }).length,
                     0, "링크로 열었을 뿐인데 보냈다");
}

// --- ④ 리마인드 주소는 그대로 리마인드 ---------------------------------------------
{
  const t = open("?mode=sourcing&topic=sourcing_remind&contacts=101,102");
  assert.deepStrictEqual(topic(t.dom), ["sourcing_remind"]);
  assert.deepStrictEqual(checkedSourcing(t.dom), ["102"],
                         "리마인드에 제안 대기중인 분이 골라졌다");
}

console.log("ok - 딜 제안 관리 · 참여 안내 링크로 열기 · 대상만 미리 고름");
