// 딜 소개 — **고른 차례가 곧 번호다.** (node tests/js/deals_pick_order_test.js)
//
// 문구는 `1) …` `2) …` 로 번호를 붙여 나가고, 투자사는 그 번호로 기억해서
// "2번 자료 주세요" 라고 답한다. 그런데 화면은 고른 차례를 안 들고 있었다 —
// `querySelectorAll(".company-cb")` 이 주는 것은 **목록에 그려진 차례**라,
// 3번째 기업을 먼저 고르고 1번째를 나중에 골라도 목록 차례로 나갔다.
// 사람이 머리에 담은 차례와 실제로 나간 번호가 어긋난다.
//
// **거꾸로 고르는 경우가 이 검사의 전부다.** 차례대로 고르면 고치기 전 코드도
// 우연히 맞아서 아무것도 안 잡힌다.
//
// 세 곳이 같은 차례를 써야 한다 — 미리보기 · 실제 발송 · 예약 큐. 셋 다
// `selectedCompanyIds()` 한 자리에서 가져가지만, 한 곳이라도 딴 데서 다시
// 세면 **화면이 말하는 번호와 나간 번호가 조용히 갈린다.** 그래서 셋을 다 본다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const A = "가나애그";    // 목록 1번째
const B = "다라헬스";    // 목록 2번째
const C = "마바로보";    // 목록 3번째

function idOf(dom, name) {
  return parseInt(deals_.companyBox(dom, name).value, 10);
}

// 예약 큐 [추가] 를 누른다. 대상 그룹은 이 검사와 무관하다.
function clickQueueAdd(dom) {
  dom.document.getElementById("queue-add").fire("click");
}

function postTo(fetch, url) {
  return fetch.calls.filter(function (c) { return c.url === url; });
}

// ── 1) ★ 거꾸로 골라도 **고른 차례**로 나간다 ──────────────────────────────
//
// C → A → B 로 고른다. 목록 차례(A, B, C)와 다르다.
{
  const fetch = deals_.fakeFetch([]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.toggleCompany(dom, C);
  deals_.toggleCompany(dom, A);
  deals_.toggleCompany(dom, B);

  // 미리보기는 `setTimeout` 뒤에 나가는데 검사판의 `setTimeout` 은 아무것도
  // 안 한다 — [미리보기 새로고침] 을 눌러 그 자리를 그대로 부른다.
  dom.document.getElementById("refresh-preview").fire("click");

  const previews = postTo(fetch, "/api/deals/preview");
  assert.strictEqual(previews.length, 1, "미리보기를 부르지 않았다");
  assert.deepStrictEqual(
    previews[0].body.company_ids,
    [idOf(dom, C), idOf(dom, A), idOf(dom, B)],
    "미리보기가 **목록 차례**로 나갔다 — 고른 차례가 아니다: " +
    JSON.stringify(previews[0].body.company_ids));
}

// ── 2) ★ 카드에 **몇 번째로 골랐는지** 가 보인다 ───────────────────────────
//
// 화면에서 번호가 안 보이면, 미리보기 문구의 `1) 2) 3)` 이 왜 그 차례인지
// 알 수 없다. 번호는 **서버로 나가는 차례를 담은 바로 그 자리**에서 읽는다
// (`data-pick-order`) — 두 곳에 적으면 어긋나도 아무도 모른다.
{
  const dom = deals_.run(null, {});

  deals_.toggleCompany(dom, C);
  deals_.toggleCompany(dom, A);
  deals_.toggleCompany(dom, B);

  assert.deepStrictEqual(
    deals_.pickNumbers(dom),
    { [A]: "2", [B]: "3", [C]: "1" },
    "고른 차례가 카드에 안 적혔다: " + JSON.stringify(deals_.pickNumbers(dom)));
}

// ── 3) ★ 체크를 풀면 **뒤 번호가 당겨진다** ────────────────────────────────
//
// C(1) A(2) B(3) 에서 A 를 풀면 B 가 2번이 되어야 한다. 번호가 비면 문구의
// `1) 3)` 과 화면이 어긋나고, 사람은 3번이 나가는 줄 안다.
{
  const fetch = deals_.fakeFetch([]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.toggleCompany(dom, C);
  deals_.toggleCompany(dom, A);
  deals_.toggleCompany(dom, B);
  deals_.toggleCompany(dom, A);          // 다시 눌러 뺀다

  assert.deepStrictEqual(
    deals_.pickNumbers(dom),
    { [A]: null, [B]: "2", [C]: "1" },
    "체크를 풀었는데 뒤 번호가 안 당겨졌다: " + JSON.stringify(deals_.pickNumbers(dom)));

  // 뺐다가 다시 고르면 **맨 뒤**다 — 아까 쓰던 번호로 되돌아가면, 사람은
  // 방금 고른 것이 앞으로 끼어든 줄 모른 채 보낸다.
  deals_.toggleCompany(dom, A);
  assert.deepStrictEqual(
    deals_.pickNumbers(dom),
    { [A]: "3", [B]: "2", [C]: "1" },
    "다시 고른 기업이 맨 뒤로 안 갔다: " + JSON.stringify(deals_.pickNumbers(dom)));

  dom.document.getElementById("refresh-preview").fire("click");
  const previews = postTo(fetch, "/api/deals/preview");
  assert.deepStrictEqual(
    previews[previews.length - 1].body.company_ids,
    [idOf(dom, C), idOf(dom, B), idOf(dom, A)],
    "화면 번호와 서버로 나간 차례가 다르다");
}

// ── 4) ★ 실제 발송도 같은 차례다 ───────────────────────────────────────────
//
// 미리보기만 맞고 발송이 다르면 제일 나쁘다 — 사람이 눈으로 확인한 문구와
// 다른 것이 실투자사 카톡방으로 나가고, 되돌릴 수가 없다.
{
  const fetch = deals_.fakeFetch([{ ok: true, d: { job_id: 5, total: 1 } }]);
  const dom = deals_.run(null, { fetch: fetch, confirm: function () { return true; } });

  deals_.toggleCompany(dom, C);
  deals_.toggleCompany(dom, A);
  deals_.toggleCompany(dom, B);
  // 받는 사람이 하나는 있어야 [발송] 이 눌린다.
  const person = dom.cards[0].querySelector(".contact-cb");
  person.checked = true;
  person.fire("change");

  dom.document.getElementById("send-btn").fire("click");

  const sends = postTo(fetch, "/api/deals/send");
  assert.strictEqual(sends.length, 1, "발송을 부르지 않았다");
  assert.deepStrictEqual(
    sends[0].body.company_ids,
    [idOf(dom, C), idOf(dom, A), idOf(dom, B)],
    "발송이 목록 차례로 나갔다: " + JSON.stringify(sends[0].body.company_ids));
}

// ── 5) ★ 예약 큐에도 같은 차례가 담긴다 ────────────────────────────────────
//
// 예약은 걸어 두고 나중에 [시작] 을 누른다. 그때 나가는 번호가 예약할 때 화면에
// 보이던 번호와 다르면, 무엇이 몇 번으로 나갔는지 아무도 모른다.
{
  const fetch = deals_.fakeFetch([{ ok: true, d: { item_id: 3, target_count: 4 } }]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.toggleCompany(dom, C);
  deals_.toggleCompany(dom, A);
  deals_.toggleCompany(dom, B);

  clickQueueAdd(dom);

  const queued = postTo(fetch, "/api/deals/queue");
  assert.strictEqual(queued.length, 1, "예약을 부르지 않았다");
  assert.deepStrictEqual(
    queued[0].body.company_ids,
    [idOf(dom, C), idOf(dom, A), idOf(dom, B)],
    "예약이 목록 차례로 담겼다: " + JSON.stringify(queued[0].body.company_ids));
}

// ── 6) ★ 링크를 받아 열었을 때도 **받은 차례**다 ───────────────────────────
//
// IR 관리에서 `?companies=203,201` 로 넘어온다. 화면 목록 차례로 켜면 요청받은
// 차례가 사라진다 — 자료가 담긴 통이 요청과 다른 차례로 날아간다.
{
  const fetch = deals_.fakeFetch([]);
  const dom = deals_.run(null, {
    fetch: fetch,
    search: "?companies=203,201"
  });

  assert.deepStrictEqual(
    deals_.pickNumbers(dom),
    { [A]: "2", [B]: null, [C]: "1" },
    "링크로 받은 차례가 안 지켜졌다: " + JSON.stringify(deals_.pickNumbers(dom)));
}

console.log("deals_pick_order_test.js OK");
